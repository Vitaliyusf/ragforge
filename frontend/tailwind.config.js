/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-geist-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-geist-mono)', 'ui-monospace', 'monospace'],
      },
      colors: {
        /* New semantic tokens */
        bg:       'var(--bg)',
        'bg-subtle': 'var(--bg-subtle)',
        surface: {
          DEFAULT:  'var(--surface)',
          elevated: 'var(--surface-elevated)',
          hover:    'var(--surface-hover)',
          active:   'var(--surface-active)',
        },
        border: {
          DEFAULT: 'var(--border)',
          strong:  'var(--border-strong)',
          focus:   'var(--border-focus)',
        },
        fg: {
          DEFAULT: 'var(--fg)',
          muted:   'var(--fg-muted)',
          soft:    'var(--fg-soft)',
        },
        primary: {
          DEFAULT: 'var(--primary)',
          hover:   'var(--primary-hover)',
          fg:      'var(--primary-fg)',
          soft:    'var(--primary-soft)',
        },
        secondary: {
          DEFAULT: 'var(--secondary)',
          hover:   'var(--secondary-hover)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          soft:    'var(--accent-soft)',
        },
        success:  'var(--success)',
        'success-soft': 'var(--success-soft)',
        warning:  'var(--warning)',
        'warning-soft': 'var(--warning-soft)',
        danger:   'var(--danger)',
        'danger-soft':  'var(--danger-soft)',
        info:     'var(--info)',
        'info-soft':    'var(--info-soft)',

        /* ── Backward-compat aliases ── */
        'bg-primary':   'var(--bg)',
        'bg-secondary': 'var(--bg-subtle)',
        'bg-tertiary':  'var(--surface)',
        'bg-elevated':  'var(--surface-elevated)',
        'bg-muted':     'var(--surface-hover)',
        'text-primary': 'var(--fg)',
        'text-secondary':'var(--fg-muted)',
        'text-muted':   'var(--fg-soft)',
        'border-hover': 'var(--border-strong)',
        error:          'var(--danger)',
      },
      boxShadow: {
        sm:   'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-md)',
        md:   'var(--shadow-md)',
        lg:   'var(--shadow-lg)',
        xl:   'var(--shadow-xl)',
        glow: 'var(--shadow-glow)',
        ring: '0 0 0 3px var(--ring)',
      },
      backgroundImage: {
        'gradient-primary': 'var(--gradient-primary)',
        'gradient-subtle':  'var(--gradient-subtle)',
        'gradient-accent':  'var(--gradient-primary)',
      },
      ringColor: {
        DEFAULT: 'var(--ring)',
        primary: 'var(--ring)',
      },
      keyframes: {
        'fade-in': {
          '0%':   { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-up': {
          '0%':   { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          '0%':   { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%':      { transform: 'translateY(-6px)' },
        },
        'pulse-ring': {
          '0%':   { boxShadow: '0 0 0 0 var(--ring)' },
          '70%':  { boxShadow: '0 0 0 6px transparent' },
          '100%': { boxShadow: '0 0 0 0 transparent' },
        },
      },
      animation: {
        'fade-in':    'fade-in 0.2s ease-out both',
        'slide-up':   'slide-up 0.3s ease-out both',
        'scale-in':   'scale-in 0.2s ease-out both',
        shimmer:      'shimmer 1.5s ease-in-out infinite',
        blink:        'blink 1s infinite',
        float:        'float 3s ease-in-out infinite',
        'pulse-ring': 'pulse-ring 1.5s ease-out infinite',
      },
      transitionDuration: {
        DEFAULT: '200ms',
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
    },
  },
  plugins: [],
}
