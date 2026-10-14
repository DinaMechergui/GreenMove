/**
 * GreenMove - Scripts JavaScript Principaux
 * Gère les animations, le thème sombre/clair, la navbar glassmorphism,
 * le preloader, les compteurs CountUp.js et l'interactivité.
 */

document.addEventListener('DOMContentLoaded', () => {
  // ------------------------------------------------------------------------
  // 1. ÉCRAN DE CHARGEMENT (PRELOADER)
  // ------------------------------------------------------------------------
  const preloader = document.getElementById('page-preloader');
  if (preloader) {
    window.addEventListener('load', () => {
      setTimeout(() => {
        preloader.classList.add('fade-out');
        setTimeout(() => preloader.remove(), 500);
      }, 650);
    });
    // Sécurité si window.load tarde
    setTimeout(() => {
      if (preloader && !preloader.classList.contains('fade-out')) {
        preloader.classList.add('fade-out');
      }
    }, 1200);
  }

  // ------------------------------------------------------------------------
  // 2. GESTION DU THÈME CLAIR / SOMBRE (DATA-THEME & LOCALSTORAGE)
  // ------------------------------------------------------------------------
  const themeToggleBtn = document.getElementById('theme-toggle-btn');
  const themeIcon = document.getElementById('theme-icon');

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('greenmove_theme', theme);
    if (themeIcon) {
      if (theme === 'dark') {
        themeIcon.classList.remove('bi-moon-stars-fill');
        themeIcon.classList.add('bi-sun-fill');
      } else {
        themeIcon.classList.remove('bi-sun-fill');
        themeIcon.classList.add('bi-moon-stars-fill');
      }
    }
  }

  // Détection du thème initial (Par défaut : mode clair doux et lumineux)
  const savedTheme = localStorage.getItem('greenmove_theme');
  if (savedTheme === 'dark') {
    applyTheme('dark');
  } else {
    applyTheme('light');
  }

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      applyTheme(newTheme);
    });
  }

  // ------------------------------------------------------------------------
  // 3. NAVBAR GLASSMORPHISME & BARRE DE PROGRESSION AU SCROLL
  // ------------------------------------------------------------------------
  const navbar = document.querySelector('.navbar-greenmove');
  const progressBar = document.getElementById('reading-progress-bar');

  window.addEventListener('scroll', () => {
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const docHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;

    // Barre de progression
    if (progressBar && docHeight > 0) {
      const scrollPercent = (scrollTop / docHeight) * 100;
      progressBar.style.width = `${scrollPercent}%`;
    }

    // Navbar compacte au scroll
    if (navbar) {
      if (scrollTop > 40) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }
    }
  });

  // ------------------------------------------------------------------------
  // 4. PARALLAXE DES FEUILLES SVG DANS LE HERO
  // ------------------------------------------------------------------------
  const heroSection = document.querySelector('.hero-section');
  const floatingLeaves = document.querySelectorAll('.floating-leaf');

  if (heroSection && floatingLeaves.length > 0 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    heroSection.addEventListener('mousemove', (e) => {
      const { clientX, clientY } = e;
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;

      floatingLeaves.forEach((leaf, idx) => {
        const factor = (idx + 1) * 0.025;
        const moveX = (clientX - centerX) * factor;
        const moveY = (clientY - centerY) * factor;
        leaf.style.transform = `translate(${moveX}px, ${moveY}px)`;
      });
    });
  }

  // ------------------------------------------------------------------------
  // 5. TOASTS BOOTSTRAP AUTOMATIQUES
  // ------------------------------------------------------------------------
  const toastElements = document.querySelectorAll('.toast');
  toastElements.forEach((toastEl) => {
    const toast = new bootstrap.Toast(toastEl, { delay: 4500 });
    toast.show();
  });

  // ------------------------------------------------------------------------
  // 6. EFFET RIPPLE SUR LES BOUTONS & SPINNER FORMULAIRE
  // ------------------------------------------------------------------------
  document.querySelectorAll('.btn-green-primary, .btn-lime, .btn-green-outline').forEach((btn) => {
    btn.addEventListener('click', function (e) {
      const circle = document.createElement('span');
      const diameter = Math.max(this.clientWidth, this.clientHeight);
      const radius = diameter / 2;

      const rect = this.getBoundingClientRect();
      circle.style.width = circle.style.height = `${diameter}px`;
      circle.style.left = `${e.clientX - rect.left - radius}px`;
      circle.style.top = `${e.clientY - rect.top - radius}px`;
      circle.classList.add('ripple');

      const ripple = this.querySelector('.ripple');
      if (ripple) ripple.remove();

      this.appendChild(circle);
    });
  });

  // Spinner automatique sur submit des formulaires
  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', function () {
      const submitBtn = this.querySelector('button[type="submit"]');
      if (submitBtn && !submitBtn.dataset.noSpinner) {
        submitBtn.disabled = true;
        const originalHtml = submitBtn.innerHTML;
        submitBtn.innerHTML = `
          <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
          <span>Traitement en cours...</span>
        `;
        // Restauration de sécurité après 8s
        setTimeout(() => {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalHtml;
        }, 8000);
      }
    });
  });

  // ------------------------------------------------------------------------
  // 7. COMPTEURS COUNTUP.JS AVEC INTERSECTION OBSERVER
  // ------------------------------------------------------------------------
  const statsSection = document.querySelector('.stats-section');
  if (statsSection && typeof countUp !== 'undefined') {
    let countersStarted = false;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && !countersStarted) {
          countersStarted = true;
          document.querySelectorAll('[data-counter-target]').forEach((el) => {
            const targetVal = parseFloat(el.getAttribute('data-counter-target')) || 0;
            const decimals = targetVal % 1 !== 0 ? 1 : 0;
            const anim = new countUp.CountUp(el, targetVal, {
              duration: 2.5,
              decimalPlaces: decimals,
              useEasing: true,
            });
            if (!anim.error) {
              anim.start();
            } else {
              el.textContent = targetVal;
            }
          });
        }
      });
    }, { threshold: 0.3 });

    observer.observe(statsSection);
  }

  // ------------------------------------------------------------------------
  // 8. INITIALISATION AOS (ANIMATE ON SCROLL)
  // ------------------------------------------------------------------------
  if (typeof AOS !== 'undefined') {
    AOS.init({
      duration: 750,
      once: true,
      easing: 'ease-out-cubic',
      offset: 60,
    });
  }

  // ------------------------------------------------------------------------
  // 9. INITIALISATION VANILLA-TILT
  // ------------------------------------------------------------------------
  if (typeof VanillaTilt !== 'undefined' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    VanillaTilt.init(document.querySelectorAll('[data-tilt]'), {
      max: 10,
      speed: 400,
      glare: true,
      'max-glare': 0.15,
      perspective: 1000,
    });
  }

  // ------------------------------------------------------------------------
  // 10. INITIALISATION DU CAROUSEL SWIPER
  // ------------------------------------------------------------------------
  if (typeof Swiper !== 'undefined') {
    new Swiper('.testimonials-swiper', {
      slidesPerView: 1,
      spaceBetween: 24,
      loop: true,
      autoplay: {
        delay: 5000,
        disableOnInteraction: false,
      },
      pagination: {
        el: '.swiper-pagination',
        clickable: true,
      },
      navigation: {
        nextEl: '.swiper-button-next',
        prevEl: '.swiper-button-prev',
      },
      breakpoints: {
        768: {
          slidesPerView: 2,
        },
        1024: {
          slidesPerView: 3,
        },
      },
    });
  }
});
