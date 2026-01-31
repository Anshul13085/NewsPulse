import React, { useEffect, useState } from "react";
import "./App.css";

// --- MAIN COMPONENT ---
export default function App() {
  // Existing State
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filters, setFilters] = useState({
    language: "",
    sentiment: "",
    bias: ""
  });
  const [ingesting, setIngesting] = useState(false);
  const [ingestStatus, setIngestStatus] = useState(null);

  // --- NEW PERSONALIZATION STATE ---
  const [user, setUser] = useState(null); // Stores { email, watchlist }
  const [view, setView] = useState('news'); // 'news', 'login', 'watchlist'

  // Load User from LocalStorage on mount
  useEffect(() => {
    const savedEmail = localStorage.getItem('user_email');
    if (savedEmail) {
      // Auto-login to get fresh watchlist
      fetch('http://localhost:8000/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: savedEmail })
      })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setUser(data.user);
        }
      })
      .catch(err => console.error("Auto-login failed", err));
    }
    
    console.log('DEBUG - Component mounted, fetching initial articles...');
    fetchArticles();
  }, []);

  // --- EXISTING FUNCTIONS (Unchanged) ---
  const fetchArticles = async (query = "", currentFilters = filters) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (query) params.append('q', query);
      if (currentFilters.language) params.append('language', currentFilters.language);
      if (currentFilters.sentiment) params.append('sentiment', currentFilters.sentiment);
      if (currentFilters.bias) params.append('bias', currentFilters.bias);
      params.append('size', '20');
      
      const response = await fetch(`http://localhost:8000/articles/search?${params}`);
      const data = await response.json();
      setArticles(data.results || []);
    } catch (error) {
      console.error('Error fetching articles:', error);
      setArticles([]);
    }
    setLoading(false);
  };

  const ingestArticles = async () => {
    setIngesting(true);
    setIngestStatus(null);
    try {
      const response = await fetch('http://localhost:8000/ingest/run?limit_per_feed=20', { method: 'POST' });
      const data = await response.json();
      setIngestStatus(data);
      if (!data.error) fetchArticles(searchQuery, filters);
    } catch (error) {
      setIngestStatus({ error: 'Failed to ingest articles' });
    }
    setIngesting(false);
  };

  const handleSearch = () => fetchArticles(searchQuery, filters);

  const handleFilterChange = (filterType, value) => {
    const newFilters = { ...filters, [filterType]: value };
    setFilters(newFilters);
    fetchArticles(searchQuery, newFilters);
  };

  // --- NEW PERSONALIZATION FUNCTIONS ---
  const handleLogin = (userData) => {
    setUser(userData);
    localStorage.setItem('user_email', userData.email);
    setView('news'); // Go back to news after login
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('user_email');
    setView('news');
  };

  const handleUpdateWatchlist = (newWatchlist) => {
    setUser({ ...user, watchlist: newWatchlist });
  };

  // --- RENDER ---
  return (
    <div className="container">
      <header className="header">
        <h1 style={{ cursor: 'pointer' }} onClick={() => setView('news')}>NewsPulse</h1>
        
        <div className="header-controls" style={{ display: 'flex', gap: '12px' }}>
          {/* Ingest Button (Blue) */}
          <button 
            onClick={ingestArticles} 
            disabled={ingesting}
            className={`nav-btn btn-ingest ${ingesting ? 'loading' : ''}`}
          >
            {ingesting ? '⏳ Ingesting...' : '📥 Ingest News'}
          </button>

          {/* User Controls */}
          {user ? (
            <>
              {/* Watchlist Button (Gold) */}
              <button className="nav-btn btn-watchlist" onClick={() => setView('watchlist')}>
                🔔 My Watchlist
              </button>
              
              {/* Logout Button (Red) */}
              <button className="nav-btn btn-logout" onClick={handleLogout}>
                Logout
              </button>
            </>
          ) : (
            <button className="nav-btn btn-ingest" onClick={() => setView('login')}>
              👤 Login
            </button>
          )}
        </div>
      </header>

      {/* VIEW ROUTING */}
      {view === 'login' && <LoginView onLogin={handleLogin} onCancel={() => setView('news')} />}
      
      {view === 'watchlist' && user && (
        <WatchlistView 
          user={user} 
          onUpdate={handleUpdateWatchlist} 
          onClose={() => setView('news')} 
        />
      )}

      {/* NEWS FEED VIEW (Only show if not in Login/Watchlist) */}
      {view === 'news' && (
        <>
          {ingestStatus && (
            <div className={`status ${ingestStatus.error ? 'error' : 'success'}`}>
              {ingestStatus.error || `Successfully ingested ${ingestStatus.indexed} articles`}
            </div>
          )}

          <div className="search-section">
            <div className="search-bar">
              <input
                type="text"
                placeholder="Search articles..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              />
              <button onClick={handleSearch}>Search</button>
            </div>

            <div className="filters">
              <select value={filters.language} onChange={(e) => handleFilterChange('language', e.target.value)}>
                <option value="">All Languages</option>
                <option value="en">English</option>
                <option value="hi">Hindi</option>
              </select>
              <select value={filters.sentiment} onChange={(e) => handleFilterChange('sentiment', e.target.value)}>
                <option value="">All Sentiments</option>
                <option value="positive">Positive</option>
                <option value="neutral">Neutral</option>
                <option value="negative">Negative</option>
              </select>
              <select value={filters.bias} onChange={(e) => handleFilterChange('bias', e.target.value)}>
                <option value="">All Bias Types</option>
                <option value="neutral">Neutral</option>
                <option value="left-leaning">Left-leaning</option>
                <option value="right-leaning">Right-leaning</option>
              </select>
            </div>
          </div>

          {loading ? (
            <div className="loading"><p>Loading articles...</p></div>
          ) : (
            <>
              <div style={{ background: '#f0f0f0', padding: '10px', fontSize: '12px' }}>
                <strong>DEBUG:</strong> Found {articles.length} articles
              </div>

              {articles.length === 0 ? (
                <div className="no-articles"><p>No articles found.</p></div>
              ) : (
                <div className="articles-grid">
                  {articles.map((article, idx) => (
                    <ArticleCard key={idx} article={article} />
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

// --- SUB-COMPONENTS (Keep file clean) ---

function ArticleCard({ article }) {
  return (
    <div className="article-card">
      <div className="article-header">
        <h2>{article.title || 'Untitled'}</h2>
        <a href={article.url} target="_blank" rel="noopener noreferrer">🔗</a>
      </div>
      <div className="article-meta">
        <span className="source">{article.source_name || 'Unknown'}</span>
        {article.published_date && (
          <span className="date">{new Date(article.published_date).toLocaleDateString()}</span>
        )}
      </div>
      
      <div className="analysis-badges">
        <span className={`badge sentiment-${article.sentiment_overall || 'unknown'}`}>
          {article.sentiment_overall || 'Unknown'} 
          {article.sentiment_score && ` ${(article.sentiment_score * 100).toFixed(0)}%`}
        </span>
        <span className={`badge bias-${(article.bias_overall || 'unknown').replace('-', '')}`}>
          {article.bias_overall || 'Unknown'}
        </span>
      </div>

      <div className="summary">
        <strong>Summary:</strong>
        <p>{article.summary || "No summary available"}</p>
      </div>

      {article.entities && article.entities.length > 0 && (
        <div className="entities">
          <strong>Entities:</strong>
          <div className="entity-tags">
            {article.entities.slice(0, 5).map((e, i) => (
              <span key={i} className="entity-tag">{e.name}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function LoginView({ onLogin, onCancel }) {
  const [email, setEmail] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if(!email) return;
    
    try {
      const res = await fetch('http://localhost:8000/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await res.json();
      if (data.status === 'success') {
        onLogin(data.user);
      }
    } catch (err) {
      alert("Login failed. Is the backend running?");
    }
  };

  return (
    <div className="auth-container" style={{ textAlign: 'center', padding: '50px' }}>
      <h2>Login / Register</h2>
      <p>Enter your email to manage your watchlist.</p>
      <form onSubmit={handleSubmit} style={{ marginTop: '20px' }}>
        <input 
          type="email" 
          placeholder="yourname@example.com" 
          value={email}
          onChange={e => setEmail(e.target.value)}
          style={{ padding: '10px', width: '300px', marginRight: '10px' }}
          required
        />
        <button type="submit" style={{ padding: '10px 20px', background: '#007bff', color: 'white', border: 'none', cursor: 'pointer' }}>
          Enter
        </button>
      </form>
      <button onClick={onCancel} style={{ marginTop: '20px', background: 'transparent', border: 'none', textDecoration: 'underline', cursor: 'pointer' }}>
        Cancel
      </button>
    </div>
  );
}

function WatchlistView({ user, onUpdate, onClose }) {
  const [newTopic, setNewTopic] = useState('');
  const [topics, setTopics] = useState(user.watchlist || []);

  const addTopic = async () => {
    if (!newTopic) return;
    const updated = [...topics, newTopic];
    setTopics(updated);
    setNewTopic('');
    
    // Sync with backend
    await fetch('http://localhost:8000/user/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: user.email, watchlist: updated })
    });
    onUpdate(updated);
  };

  const removeTopic = async (topicToRemove) => {
    const updated = topics.filter(t => t !== topicToRemove);
    setTopics(updated);
    
    // Sync with backend
    await fetch('http://localhost:8000/user/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: user.email, watchlist: updated })
    });
    onUpdate(updated);
  };

  return (
    <div style={{ padding: '20px' }}>
      <button className="nav-btn btn-back" onClick={onClose} style={{ marginBottom: '20px' }}>
        ← Back to News Feed
      </button>
      
      <div className="watchlist-dashboard">
        {/* LEFT SIDE: INFO PANEL */}
        <div className="watchlist-sidebar">
          <h3>⚡ Intelligent Agent</h3>
          <p style={{ fontSize: '13px', color: '#666', marginBottom: '20px' }}>
            Logged in as: <strong>{user.email}</strong>
          </p>

          <ul className="feature-list">
            <li>
              <span>🕵️</span>
              <div>
                <strong>Autonomous Patrol</strong>
                <br/>The Agent monitors these topics 24/7 so you don't have to.
              </div>
            </li>
            <li>
              <span>🚨</span>
              <div>
                <strong>Crisis Detection</strong>
                <br/>Instantly alerts you if negative sentiment spikes for your topics.
              </div>
            </li>
            <li>
              <span>📧</span>
              <div>
                <strong>Smart Briefings</strong>
                <br/>Receive automated HTML reports summarizing the threats.
              </div>
            </li>
          </ul>
        </div>

        {/* RIGHT SIDE: MANAGEMENT */}
        <div className="watchlist-main">
          <h2>Monitor New Topic</h2>
          <p style={{ color: '#7f8c8d', marginBottom: '20px' }}>
            Add companies, people, or keywords. The Agent will start tracking them in the next cycle.
          </p>
          
          <div style={{ display: 'flex', gap: '10px', marginBottom: '30px' }}>
            <input 
              value={newTopic}
              onChange={e => setNewTopic(e.target.value)}
              placeholder="E.g. Bitcoin, Adani, Elections..."
              style={{ 
                flex: 1, 
                padding: '12px 15px', 
                border: '1px solid #ddd', 
                borderRadius: '6px',
                fontSize: '16px'
              }}
              onKeyPress={(e) => e.key === 'Enter' && addTopic()}
            />
            <button 
              onClick={addTopic} 
              className="nav-btn btn-ingest"
              style={{ padding: '0 25px' }}
            >
              Add Tracker
            </button>
          </div>

          <div style={{ borderTop: '1px solid #eee', paddingTop: '20px' }}>
            <h4 style={{ margin: '0 0 15px 0', color: '#999', textTransform: 'uppercase', fontSize: '12px', letterSpacing: '1px' }}>
              Currently Monitoring ({topics.length})
            </h4>
            
            <div className="tag-cloud">
              {topics.length === 0 && <p style={{ color: '#ccc', fontStyle: 'italic' }}>No active trackers.</p>}
              {topics.map((t, i) => (
                <div key={i} className="watch-tag">
                  <span style={{ color: '#27ae60' }}>●</span> {t}
                  <span 
                    className="remove-tag"
                    onClick={() => removeTopic(t)}
                  >
                    ×
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}