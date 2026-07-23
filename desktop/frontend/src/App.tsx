import { useState } from 'react';
import { Rail, type ScreenId } from './components/Rail';
import { ThemeToggle } from './components/ThemeToggle';
import { Wordmark } from './components/Wordmark';
import { Home } from './screens/Home';
import { Sections } from './screens/Sections';
import { Videos } from './screens/Videos';
import { Settings } from './screens/Settings';
import type { Course } from './types';

export default function App() {
  const [screen, setScreen] = useState<ScreenId>('home');
  const [course, setCourse] = useState<Course | null>(null);

  function openCourse(c: Course) {
    setCourse(c);
    setScreen('sections');
  }

  return (
    <div className="stage">
      <div className="glow-field">
        <div className="blob blob-a" />
        <div className="blob blob-b" />
      </div>

      <Rail active={screen} onNavigate={setScreen} />

      <main className="main">
        <div className="topline">
          <div>
            <div className="eyebrow">Bonjour, Professeur</div>
            <Wordmark />
          </div>
          <ThemeToggle />
        </div>

        {screen === 'home' && <Home onCourseReady={openCourse} />}
        {screen === 'sections' && (
          <Sections course={course} onCourseUpdate={setCourse} onFinished={() => setScreen('videos')} />
        )}
        {screen === 'videos' && <Videos onResume={openCourse} />}
        {screen === 'settings' && <Settings />}
      </main>
    </div>
  );
}
