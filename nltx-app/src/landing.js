/* ===== NLTX Landing Page JS ===== */

// ===== NAVBAR SCROLL =====
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  if (window.scrollY > 20) navbar.classList.add('scrolled');
  else navbar.classList.remove('scrolled');
});

// ===== HAMBURGER =====
const hamburger = document.getElementById('hamburger');
if (hamburger) {
  hamburger.addEventListener('click', () => {
    document.querySelector('.nav-links')?.classList.toggle('mobile-open');
  });
}

// ===== PARTICLE CANVAS =====
const canvas = document.getElementById('particleCanvas');
if (canvas) {
  const ctx = canvas.getContext('2d');
  let particles = [];
  const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
  resize();
  window.addEventListener('resize', resize);

  class Particle {
    constructor() { this.reset(); }
    reset() {
      this.x = Math.random() * canvas.width;
      this.y = Math.random() * canvas.height;
      this.size = Math.random() * 2 + 0.5;
      this.speedX = (Math.random() - 0.5) * 0.4;
      this.speedY = (Math.random() - 0.5) * 0.4;
      this.opacity = Math.random() * 0.5 + 0.1;
      this.color = ['#7c3aed','#2563eb','#06b6d4'][Math.floor(Math.random()*3)];
    }
    update() {
      this.x += this.speedX; this.y += this.speedY;
      if (this.x < 0 || this.x > canvas.width || this.y < 0 || this.y > canvas.height) this.reset();
    }
    draw() {
      ctx.globalAlpha = this.opacity;
      ctx.fillStyle = this.color;
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  for (let i = 0; i < 80; i++) particles.push(new Particle());

  function animateParticles() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => { p.update(); p.draw(); });
    // Draw connections
    ctx.globalAlpha = 1;
    particles.forEach((p1, i) => {
      particles.slice(i+1).forEach(p2 => {
        const d = Math.hypot(p1.x-p2.x, p1.y-p2.y);
        if (d < 100) {
          ctx.globalAlpha = (1 - d/100) * 0.08;
          ctx.strokeStyle = '#7c3aed';
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.stroke();
        }
      });
    });
    ctx.globalAlpha = 1;
    requestAnimationFrame(animateParticles);
  }
  animateParticles();
}

// ===== CHAT DEMO ANIMATION =====
const chatDemo = document.getElementById('chatDemo');
const botTyping = document.getElementById('botTyping');
if (chatDemo && botTyping) {
  const conversations = [
    {
      user: 'Send 50 USDT to Alice for coffee ☕',
      bot: '✅ Processed! Sent 50 USDT to @alice\n💸 Gas: $0.08 · Polygon\n⏱ 30s undo window active'
    },
    {
      user: "What's my ETH balance?",
      bot: '📊 Your ETH balance:\n2.4831 ETH ≈ $6,183.40\n+2.4% today'
    },
    {
      user: 'Schedule $200 USDT to savings on the 1st',
      bot: '⏰ Recurring payment scheduled!\n$200 USDT → @savings\nFirst payment: March 1st 2026'
    },
    {
      user: 'Swap 0.5 ETH to USDC at best rate',
      bot: '🔄 Swap preview:\n0.5 ETH → 1,247.30 USDC\nRoute: Uniswap V3 · Confirm?'
    }
  ];

  let convIdx = 0;
  function runConversation() {
    const conv = conversations[convIdx % conversations.length];
    convIdx++;
    // Remove old messages
    const oldMsgs = chatDemo.querySelectorAll('.msg');
    oldMsgs.forEach(m => { if (m !== botTyping) m.remove(); });
    // Show typing
    botTyping.classList.remove('hidden');
    botTyping.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    // After a moment, show user message
    setTimeout(() => {
      const userMsg = document.createElement('div');
      userMsg.className = 'msg user';
      userMsg.textContent = conv.user;
      chatDemo.insertBefore(userMsg, botTyping);
      botTyping.style.display = 'block';
    }, 500);
    // Then bot response
    setTimeout(() => {
      botTyping.style.display = 'none';
      const botMsg = document.createElement('div');
      botMsg.className = 'msg bot success';
      botMsg.style.whiteSpace = 'pre-line';
      botMsg.textContent = conv.bot;
      chatDemo.appendChild(botMsg);
    }, 2500);
  }

  runConversation();
  setInterval(runConversation, 5000);
}

// ===== INTERSECTION OBSERVER (animate on scroll) =====
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.feature-card, .step, .chain-card, .usecase-card').forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(20px)';
  el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
  observer.observe(el);
});
