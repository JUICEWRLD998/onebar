import { LazyMotion, MotionConfig, domAnimation } from "motion/react";
import { useEffect } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Ask } from "./routes/Ask";
import { How } from "./routes/How";
import { Results } from "./routes/Results";
import { TracePage } from "./routes/TracePage";

function ScrollReset() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function NotFound() {
  useEffect(() => {
    document.title = "Not found | OneBar";
  }, []);
  return (
    <div style={{ maxWidth: "var(--shell)", margin: "0 auto", padding: "var(--s-7) var(--gutter)" }}>
      <h1>That page does not exist</h1>
      <p style={{ marginTop: "var(--s-3)" }}>
        Check the address, or <Link to="/">go back to asking a question</Link>.
      </p>
    </div>
  );
}

export function App() {
  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domAnimation} strict>
        <a className="skip" href="#main">
          Skip to content
        </a>
        <ScrollReset />
        <Header />
        <main id="main" tabIndex={-1} style={{ flex: 1, outline: "none" }}>
          <Routes>
            <Route path="/" element={<Ask />} />
            <Route path="/results" element={<Results />} />
            <Route path="/how-it-works" element={<How />} />
            <Route path="/trace/:id" element={<TracePage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
        <Footer />
      </LazyMotion>
    </MotionConfig>
  );
}
