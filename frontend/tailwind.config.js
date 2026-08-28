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
        /* Work happening right now. See --status-live in globals.css. */
        'status-live':  'var(--status-live)',

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
        sm:      'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-md)',
        md:      'var(--shadow-md)',
        lg:      'var(--shadow-lg)',
        xl:      'var(--shadow-xl)',
      },
      ringColor: {
        DEFAULT: 'var(--ring)',
        primary: 'var(--ring)',
      },
      /* The motion scale lives in globals.css so CSS and Tailwind agree. */
      transitionDuration: {
        DEFAULT: 'var(--motion-normal)',
        fast:    'var(--motion-fast)',
        normal:  'var(--motion-normal)',
        slow:    'var(--motion-slow)',
      },
      transitionTimingFunction: {
        emphasized: 'var(--motion-easing)',
      },
      /* Calmer than Tailwind's defaults. The app leans on rounded-lg/xl/2xl
         everywhere, so tightening these three reshapes every surface at once. */
      borderRadius: {
        /* Semantic first: controls and surfaces name their own radius. */
        control: 'var(--radius-control)',
        surface: 'var(--radius-surface)',
        lg:    '0.5rem',   /* 8px  */
        xl:    '0.625rem', /* 10px */
        '2xl': '0.75rem',  /* 12px */
        '3xl': '1rem',     /* 16px */
      },
    },
  },
  plugins: [],
}
