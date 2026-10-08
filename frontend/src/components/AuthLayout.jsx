import { ArrowLeft, Sun } from 'lucide-react'

export default function AuthLayout({ children, title, intro, wide = false }) {
  return <main className={`login-shell auth-shell ${wide ? 'auth-wide' : ''}`}>
    <img className="library-backdrop" src="/ohayo-library.png" alt="" fetchPriority="high" />
    <div className="login-surface">
      <header className="login-header">
        <a className="wordmark" href="/" aria-label="OHAYO, trang đăng nhập"><Sun size={31} className="brand-sun" aria-hidden="true" />OHAYO<span className="brand-period">.</span></a>
        <span className="header-caption">Hệ thống quản lý học tập thông minh</span>
      </header>
      <section className="login-content" aria-labelledby="auth-title">
        <a className="auth-back" href="/"><ArrowLeft size={16} aria-hidden="true" />Đăng nhập</a>
        <h1 id="auth-title">{title}</h1>
        {intro && <p className="login-intro">{intro}</p>}
        {children}
      </section>
      <footer className="login-footer"><span>© {new Date().getFullYear()} OHAYO</span></footer>
    </div>
    <aside className="photo-caption" aria-label="Thông điệp OHAYO"><span className="photo-eyebrow">MỖI NGÀY, MỘT ĐIỀU MỚI</span><p>Tri thức bắt đầu<br />từ sự tò mò.</p><span className="photo-caption-line" /></aside>
  </main>
}
