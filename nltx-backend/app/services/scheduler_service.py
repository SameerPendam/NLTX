"""
NLTX Scheduler Service — Autonomous Background Processor
Handles: Scheduled payments, Auto-resets of spending limits
"""
import logging
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models.database import ScheduledPayment, Transaction, TxType, TxStatus, User, SpendingLimit
from app.services.blockchain_service import get_blockchain_service

logger = logging.getLogger("nltx.scheduler")

def process_scheduled_payments():
    """
    Background worker loop to process recurring payments.
    """
    logger.info("⚡ NLTX Autonomous Scheduler started.")
    
    while True:
        db = SessionLocal()
        try:
            # 1. Find due payments
            now = datetime.utcnow()
            due_payments = db.query(ScheduledPayment).filter(
                ScheduledPayment.is_active == True,
                ScheduledPayment.next_run <= now
            ).all()
            
            if due_payments:
                logger.info(f"⏰ Found {len(due_payments)} due payments.")
                
            for pay in due_payments:
                execute_payment(db, pay)
            
            # 2. Daily Limit Resets (Reset if last_reset_daily is > 1 day ago)
            reset_spending_limits(db)
            
        except Exception as e:
            logger.error(f"❌ Scheduler Error: {e}")
        finally:
            db.close()
            
        # Sleep for 1 minute
        time.sleep(60)

def execute_payment(db: Session, pay: ScheduledPayment):
    """Execute a single scheduled payment and update its next run date."""
    try:
        logger.info(f"执行 (Execute) Recurring: {pay.amount} {pay.token} from user {pay.user_id} to {pay.to_username or pay.to_address}")
        
        # Simulated blockchain execution
        bc = get_blockchain_service()
        # Fallback addresses for demo
        from_addr = "0xDemoSenderAddress0000000000000000000001"
        to_addr = pay.to_address or "0xDemoRecipientAddress000000000000000000001"
        
        tx_result = bc.simulate_transaction(from_addr, to_addr, pay.amount, pay.token, pay.network.value if hasattr(pay.network, 'value') else pay.network)
        
        # Create Transaction record
        tx = Transaction(
            user_id=pay.user_id,
            tx_type=TxType.SCHEDULE,
            status=TxStatus.CONFIRMED,
            network=pay.network,
            from_address=from_addr,
            to_address=to_addr,
            to_username=pay.to_username,
            amount=pay.amount,
            token=pay.token,
            usd_value=pay.amount, # Simple 1:1 for demo
            gas_fee_usd=tx_result.get("gas_usd", 0),
            memo=f"Auto-payment: {pay.memo or pay.frequency}",
            tx_hash=tx_result.get("tx_hash"),
            executed_at=datetime.utcnow(),
            confirmed_at=datetime.utcnow()
        )
        db.add(tx)
        
        # Update pay record
        pay.last_run = datetime.utcnow()
        
        # Calculate next run
        freq = pay.frequency.lower()
        if freq == "daily":
            pay.next_run = pay.next_run + timedelta(days=1)
        elif freq == "weekly":
            pay.next_run = pay.next_run + timedelta(weeks=1)
        elif freq == "monthly":
            # Rough monthly add
            pay.next_run = pay.next_run + timedelta(days=30)
        else:
            pay.is_active = False # Unknown frequency
            
        db.commit()
        logger.info(f"✅ Success: Scheduled payment executed. Next run: {pay.next_run}")
        
    except Exception as e:
        logger.error(f"❌ Failed to execute payment {pay.id}: {e}")
        db.rollback()

def reset_spending_limits(db: Session):
    """Automatically reset daily/weekly used counters."""
    now = datetime.utcnow()
    
    # Reset daily
    daily_reset_due = db.query(SpendingLimit).filter(
        SpendingLimit.last_reset_daily <= now - timedelta(days=1)
    ).all()
    
    for limit in daily_reset_due:
        limit.daily_used = 0.0
        limit.last_reset_daily = now
        
    # Reset weekly
    weekly_reset_due = db.query(SpendingLimit).filter(
        SpendingLimit.last_reset_weekly <= now - timedelta(days=7)
    ).all()
    
    for limit in weekly_reset_due:
        limit.weekly_used = 0.0
        limit.last_reset_weekly = now
        
    if daily_reset_due or weekly_reset_due:
        db.commit()
        logger.info(f"🔄 Reset {len(daily_reset_due)} daily and {len(weekly_reset_due)} weekly spending limits.")
