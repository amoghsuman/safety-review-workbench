import React, { useState } from 'react';
import LoginScreen from './components/LoginScreen';
import SessionQueue from './components/SessionQueue';
import SessionViewer from './components/SessionViewer';

export default function App() {
  const [reviewerName,     setReviewerName]     = useState('');
  const [currentScreen,    setCurrentScreen]    = useState('queue');
  const [selectedSessionId,setSelectedSessionId]= useState(null);
  const [sessionList,      setSessionList]      = useState([]);

  if (!reviewerName) {
    return <LoginScreen onLogin={setReviewerName} />;
  }

  if (currentScreen === 'session') {
    return (
      <SessionViewer
        sessionId={selectedSessionId}
        sessionList={sessionList}
        reviewerName={reviewerName}
        onBack={() => {
          setCurrentScreen('queue');
          setSelectedSessionId(null);
        }}
        onNavigate={setSelectedSessionId}
      />
    );
  }

  return (
    <SessionQueue
      reviewerName={reviewerName}
      onSelectSession={(id, list) => {
        setSelectedSessionId(id);
        setSessionList(list || []);
        setCurrentScreen('session');
      }}
    />
  );
}
