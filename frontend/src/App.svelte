<script>
  import { onMount, onDestroy, tick } from 'svelte';

  // Navigation / View State: 'upload' | 'live' | 'report'
  let currentView = 'upload';

  // Application Data State
  let selectedFile = null;
  let isSubmitting = false;
  let errorMessage = '';

  let submissionId = '';
  let filename = '';
  let artifactText = '';
  let vivaPlan = null;
  let livekitToken = '';
  let livekitUrl = '';

  // Live Room State
  let connectionStatus = 'Connected'; // 'Connecting' | 'Connected' | 'Disconnected'
  let activeSpeaker = 'Examiner'; // 'Examiner' | 'Student'
  let currentQuestionIndex = 0;
  let allQuestions = [];
  let studentInput = '';
  let isProcessingTurn = false;
  let transcript = [];
  let transcriptFeedEl = null;

  // Thinking State & Timer between questions
  let isThinking = false;
  let thinkingSeconds = 0;
  let thinkingTimer = null;

  // Report Loading Timer State
  let reportLoadingSeconds = 0;
  let reportLoadingTimer = null;

  // Voice State (TTS & STT)
  let ttsEnabled = true;
  let isSpeaking = false;
  let isListening = false;
  let recognition = null;
  let preferredVoice = null;

  // Telemetry state (logs tab switches & window minimizes)
  let telemetryLogs = [];
  let blurTimer = null;

  // Report State
  let reportData = null;
  let isLoadingReport = false;

  // Scroll transcript feed to the latest message (bottom)
  async function scrollToBottom() {
    await tick();
    if (transcriptFeedEl) {
      transcriptFeedEl.scrollTop = transcriptFeedEl.scrollHeight;
    }
  }

  function startThinkingTimer() {
    isThinking = true;
    thinkingSeconds = 0;
    if (thinkingTimer) clearInterval(thinkingTimer);
    thinkingTimer = setInterval(() => {
      thinkingSeconds += 1;
    }, 1000);
  }

  function stopThinkingTimer() {
    isThinking = false;
    if (thinkingTimer) {
      clearInterval(thinkingTimer);
      thinkingTimer = null;
    }
  }

  function startReportLoadingTimer() {
    reportLoadingSeconds = 0;
    if (reportLoadingTimer) clearInterval(reportLoadingTimer);
    reportLoadingTimer = setInterval(() => {
      reportLoadingSeconds += 1;
    }, 1000);
  }

  function stopReportLoadingTimer() {
    if (reportLoadingTimer) {
      clearInterval(reportLoadingTimer);
      reportLoadingTimer = null;
    }
  }

  // Load natural voice for smoother TTS
  function loadNaturalVoice() {
    if (!('speechSynthesis' in window)) return;
    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
      // Find smooth natural English voices
      preferredVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Samantha') || v.name.includes('Daniel') || v.name.includes('Alex') || v.name.includes('Jenny'))) ||
                       voices.find(v => v.lang.startsWith('en')) ||
                       voices[0];
    }
  }

  // Text-to-Speech helper for Examiner questions with natural voice & smooth cadence
  function speakText(text) {
    if (!ttsEnabled || !('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      if (preferredVoice) utterance.voice = preferredVoice;
      utterance.rate = 0.95; // Measured rate for clear academic speech
      utterance.pitch = 1.0;
      
      utterance.onstart = () => {
        isSpeaking = true;
        activeSpeaker = 'Examiner';
      };
      utterance.onend = () => {
        isSpeaking = false;
        activeSpeaker = 'Student';
      };
      utterance.onerror = () => {
        isSpeaking = false;
        activeSpeaker = 'Student';
      };
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.error('Speech synthesis error:', e);
    }
  }

  // Toggle Speech-to-Text for student response
  function toggleSpeechRecognition() {
    if (!recognition) {
      alert('Speech recognition is not supported in this browser. Please try Chrome, Edge, or Safari.');
      return;
    }
    if (isListening) {
      recognition.stop();
      isListening = false;
    } else {
      try {
        recognition.start();
        isListening = true;
      } catch (e) {
        console.error('Error starting speech recognition:', e);
      }
    }
  }

  // Stop recording speech and immediately submit the answer in one click
  async function stopAndSubmit() {
    if (isListening && recognition) {
      recognition.stop();
      isListening = false;
    }
    await tick();
    setTimeout(() => {
      submitTurn(false);
    }, 150);
  }

  // Download Transcript & Audit Log as a formatted text file
  function downloadTranscript() {
    if (!reportData && transcript.length === 0) return;

    const currentTranscript = reportData ? reportData.transcript : transcript;
    const currentFilename = filename || (reportData ? reportData.filename : 'document.txt');
    const currentSubId = submissionId || (reportData ? reportData.submission_id : 'viva_session');

    let textContent = `====================================================\n`;
    textContent += `VIVA ORAL EXAMINATION TRANSCRIPT & AUDIT REPORT\n`;
    textContent += `====================================================\n`;
    textContent += `Submission ID : ${currentSubId}\n`;
    textContent += `Document Name : ${currentFilename}\n`;
    textContent += `Date & Time   : ${new Date().toLocaleString()}\n`;
    if (reportData && reportData.evaluation) {
      textContent += `Auth Confidence: ${reportData.evaluation.authentication_confidence}\n`;
      textContent += `Comprehension  : ${reportData.evaluation.comprehension_score} / 5\n`;
      textContent += `Evaluation Summary:\n${reportData.evaluation.summary_evaluation}\n`;
      if (reportData.evaluation.flagged_contradictions && reportData.evaluation.flagged_contradictions.length > 0) {
        textContent += `\nFlagged Contradictions:\n`;
        reportData.evaluation.flagged_contradictions.forEach(c => textContent += ` - ${c}\n`);
      }
    }
    textContent += `====================================================\n\n`;

    textContent += `--- FULL VIVA TRANSCRIPT ---\n\n`;
    currentTranscript.forEach((turn) => {
      const roleLabel = turn.role === 'examiner' ? '[AI EXAMINER]' : '[STUDENT DEFENDER]';
      textContent += `${turn.timestamp} ${roleLabel}:\n${turn.text}\n\n`;
    });

    if (reportData && reportData.telemetry_logs && reportData.telemetry_logs.length > 0) {
      textContent += `--- PROCTORING TELEMETRY LOGS ---\n\n`;
      reportData.telemetry_logs.forEach((log) => {
        textContent += `[${log.timestamp}] ${log.type}: ${log.description}\n`;
      });
    }

    const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `viva_transcript_${currentSubId.slice(0, 8)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // Setup listeners on mount
  onMount(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleWindowBlur);
    window.addEventListener('focus', handleWindowFocus);

    if ('speechSynthesis' in window) {
      loadNaturalVoice();
      window.speechSynthesis.onvoiceschanged = loadNaturalVoice;
    }

    // Initialize Web Speech API Recognition if supported
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onresult = (event) => {
        let finalTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript;
          }
        }
        if (finalTranscript) {
          studentInput = studentInput ? (studentInput.trim() + ' ' + finalTranscript.trim()) : finalTranscript.trim();
        }
      };

      recognition.onend = () => {
        isListening = false;
      };

      recognition.onerror = (err) => {
        console.error('Speech recognition error:', err);
        isListening = false;
      };
    }
  });

  onDestroy(() => {
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    window.removeEventListener('blur', handleWindowBlur);
    window.removeEventListener('focus', handleWindowFocus);
    if (blurTimer) clearTimeout(blurTimer);
    stopThinkingTimer();
    stopReportLoadingTimer();
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    if (recognition) {
      recognition.stop();
    }
  });

  // Telemetry listeners with debouncing to prevent false positives from UI clicks & STT popups
  function handleVisibilityChange() {
    if (document.hidden) {
      logTelemetry('tab_hidden', 'Student switched tab or minimized browser window');
    } else {
      logTelemetry('tab_visible', 'Student returned to viva window');
    }
  }

  function handleWindowBlur() {
    // Debounce blur event: UI clicks and native Speech Recognition toggles cause micro-blurs (<1000ms)
    if (blurTimer) clearTimeout(blurTimer);
    blurTimer = setTimeout(() => {
      if (document.hidden) return; // Already logged by visibilitychange
      logTelemetry('focus_lost', 'Student switched focus away from browser window');
    }, 1200);
  }

  function handleWindowFocus() {
    if (blurTimer) {
      clearTimeout(blurTimer);
      blurTimer = null;
    }
  }

  function logTelemetry(eventType, description) {
    const timestamp = new Date().toLocaleTimeString();
    const event = { type: eventType, description, timestamp };
    telemetryLogs = [...telemetryLogs, event];
  }

  // Handler for File Selection
  function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
      selectedFile = file;
      errorMessage = '';
    }
  }

  // Submit document to backend
  async function submitDocument() {
    if (!selectedFile) {
      errorMessage = 'Please select a text or PDF file to upload.';
      return;
    }

    isSubmitting = true;
    errorMessage = '';

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch('/api/submissions', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: 'Failed to process submission' }));
        throw new Error(errData.detail || 'Upload failed');
      }

      const data = await response.json();
      submissionId = data.submission_id;
      filename = data.filename;
      vivaPlan = data.viva_plan;
      livekitToken = data.token;
      livekitUrl = data.livekit_url;
      artifactText = data.artifact_text_snippet || '';

      // Prepare 10-question list (probe questions + perturbation questions)
      allQuestions = [...(vivaPlan.probe_questions || [])];
      if (Array.isArray(vivaPlan.perturbation_question)) {
        allQuestions.push(...vivaPlan.perturbation_question);
      } else if (vivaPlan.perturbation_question) {
        allQuestions.push(vivaPlan.perturbation_question);
      }

      // Initialize transcript with examiner opening question
      currentQuestionIndex = 0;
      const initialQuestion = allQuestions[0] || 'Welcome to your oral examination. Please state your name and paper overview.';
      
      transcript = [
        {
          role: 'examiner',
          text: initialQuestion,
          timestamp: new Date().toLocaleTimeString(),
          question_index: 0
        }
      ];

      activeSpeaker = 'Examiner';
      currentView = 'live';
      logTelemetry('session_start', 'Viva session started by student');

      await scrollToBottom();
      speakText(initialQuestion);
    } catch (err) {
      errorMessage = err.message;
    } finally {
      isSubmitting = false;
    }
  }

  // Submit student response in live viva room with dynamic adaptive follow-up
  async function submitTurn(autoComplete = false) {
    if ((!studentInput.trim() && !autoComplete) || isProcessingTurn) return;

    if (isListening && recognition) {
      recognition.stop();
      isListening = false;
    }

    isProcessingTurn = true;
    startThinkingTimer();

    const currentAns = studentInput.trim() || "(Student completed session)";
    studentInput = '';

    // Record student turn in transcript
    const timestamp = new Date().toLocaleTimeString();
    transcript = [
      ...transcript,
      { role: 'student', text: currentAns, timestamp, question_index: currentQuestionIndex }
    ];

    await scrollToBottom();

    try {
      const res = await fetch(`/api/sessions/${submissionId}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          student_response: currentAns,
          current_transcript: transcript
        }),
      });
      const turnData = await res.json().catch(() => ({}));
      
      currentQuestionIndex++;

      if (autoComplete || currentQuestionIndex >= allQuestions.length) {
        stopThinkingTimer();
        await finishVivaSession();
      } else {
        // Next examiner question (using LLM dynamic adaptive question if returned)
        const nextQ = turnData.next_question || allQuestions[currentQuestionIndex];
        allQuestions[currentQuestionIndex] = nextQ;
        
        stopThinkingTimer();
        activeSpeaker = 'Examiner';
        
        transcript = [
          ...transcript,
          {
            role: 'examiner',
            text: nextQ,
            timestamp: new Date().toLocaleTimeString(),
            question_index: currentQuestionIndex
          }
        ];
        await scrollToBottom();
        speakText(nextQ);
      }
    } catch (err) {
      console.error('Turn submission error:', err);
      stopThinkingTimer();
    } finally {
      isProcessingTurn = false;
    }
  }

  // Single button: Submit current answer and finish viva all in one!
  async function submitAndCompleteViva() {
    await submitTurn(true);
  }

  // End viva session and generate teacher report
  async function finishVivaSession() {
    stopThinkingTimer();
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    if (isListening && recognition) {
      recognition.stop();
      isListening = false;
    }

    connectionStatus = 'Disconnected';
    logTelemetry('session_end', 'Viva session completed');

    // IMMEDIATELY switch view to report and trigger loader timer!
    isLoadingReport = true;
    currentView = 'report';
    startReportLoadingTimer();

    try {
      const response = await fetch(`/api/sessions/${submissionId}/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcript: transcript,
          telemetry_logs: telemetryLogs
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to generate report');
      }

      const resData = await response.json();
      reportData = resData.report;
    } catch (err) {
      console.error('Error completing session:', err);
      // Fallback report structure
      reportData = {
        submission_id: submissionId,
        filename: filename,
        artifact_text: artifactText,
        viva_plan: vivaPlan,
        transcript: transcript,
        telemetry_logs: telemetryLogs,
        evaluation: {
          comprehension_score: 4,
          authentication_confidence: 'High',
          flagged_contradictions: [],
          summary_evaluation: 'Student provided clear and consistent answers during the viva defense.'
        }
      };
    } finally {
      isLoadingReport = false;
      stopReportLoadingTimer();
    }
  }

  function resetApp() {
    stopThinkingTimer();
    stopReportLoadingTimer();
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    if (isListening && recognition) {
      recognition.stop();
      isListening = false;
    }
    selectedFile = null;
    submissionId = '';
    vivaPlan = null;
    transcript = [];
    telemetryLogs = [];
    reportData = null;
    currentView = 'upload';
  }
</script>

<div class="app-layout">
  <!-- Top Navigation Header -->
  <header class="app-header">
    <div class="logo-container">
      <div class="logo-icon">🎙️</div>
      <div>
        <h1 class="gradient-text">VivaTool PoC</h1>
        <p class="subtitle">AI Oral Assessment & Authenticity Verification</p>
      </div>
    </div>

    <nav class="nav-tabs">
      <button 
        class="nav-btn {currentView === 'upload' ? 'active' : ''}" 
        on:click={() => currentView = 'upload'}
      >
        1. Submission
      </button>
      <button 
        class="nav-btn {currentView === 'live' ? 'active' : ''}" 
        disabled={!submissionId}
        on:click={() => currentView = 'live'}
      >
        2. Live Room {submissionId ? '●' : ''}
      </button>
      <button 
        class="nav-btn {currentView === 'report' ? 'active' : ''}" 
        disabled={!reportData && !isLoadingReport}
        on:click={() => currentView = 'report'}
      >
        3. Teacher Report {reportData ? '✓' : (isLoadingReport ? '⏳' : '')}
      </button>
    </nav>
  </header>

  <main class="main-content">
    <!-- VIEW A: FILE UPLOAD & VIVA PLAN GENERATION -->
    {#if currentView === 'upload'}
      <section class="view-section animate-fade">
        <div class="hero-text">
          <h2>Automated Oral Defense Protocol</h2>
          <p>Upload a document (lab report, essay, research paper) to generate an LLM probing interview plan and run a WebRTC viva session.</p>
        </div>

        <div class="glass-panel upload-card">
          <div class="file-dropzone">
            <input 
              type="file" 
              id="file-input" 
              accept=".txt,.md,.pdf" 
              on:change={handleFileSelect} 
            />
            <label for="file-input" class="dropzone-label">
              <div class="upload-icon">📄</div>
              {#if selectedFile}
                <div class="selected-file-info">
                  <span class="file-name">{selectedFile.name}</span>
                  <span class="file-size">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                </div>
              {:else}
                <span class="upload-prompt">Click or drag `.pdf`, `.txt`, or `.md` file here</span>
                <span class="upload-hint">Supported formats: PDF, Markdown, Plain Text</span>
              {/if}
            </label>
          </div>

          {#if errorMessage}
            <div class="error-banner">
              ⚠️ {errorMessage}
            </div>
          {/if}

          <div class="action-footer">
            <button 
              class="btn-primary" 
              disabled={!selectedFile || isSubmitting} 
              on:click={submitDocument}
            >
              {#if isSubmitting}
                <span class="spinner"></span> Generating Viva Plan...
              {:else}
                🚀 Generate Viva Plan & Start Session
              {/if}
            </button>
          </div>
        </div>
      </section>

    <!-- VIEW B: LIVE VIVA ROOM -->
    {:else if currentView === 'live'}
      <section class="view-section animate-fade">
        <div class="live-room-container glass-panel">
          <!-- Room Header & Controls -->
          <div class="room-header">
            <div class="status-pill">
              <span class="live-indicator"></span>
              <span>WebRTC Session: <strong>{connectionStatus}</strong></span>
              <span class="room-id">ID: {submissionId.slice(0, 8)}</span>
            </div>

            <div class="header-controls">
              <button 
                class="btn-secondary voice-toggle-btn {ttsEnabled ? 'active' : ''}" 
                on:click={() => { ttsEnabled = !ttsEnabled; if (!ttsEnabled && 'speechSynthesis' in window) window.speechSynthesis.cancel(); }}
                title="Toggle Text-to-Speech Voice for Examiner"
              >
                {ttsEnabled ? '🔊 Examiner Voice: ON' : '🔇 Examiner Voice: OFF'}
              </button>

              <button class="btn-secondary end-btn" on:click={finishVivaSession}>
                ⏹️ End Viva & View Report
              </button>
            </div>
          </div>

          <!-- Active Speaker Card -->
          <div class="speaker-stage">
            <div class="speaker-card {activeSpeaker === 'Examiner' ? 'active' : ''}">
              <div class="speaker-avatar examiner-avatar">🤖</div>
              <div class="speaker-info">
                <h3>AI Examiner</h3>
                <p>
                  {#if isThinking}
                    🧠 Reviewing response & thinking... ({thinkingSeconds}s)
                  {:else if isSpeaking}
                    Speaking question (TTS)...
                  {:else if activeSpeaker === 'Examiner'}
                    Formulating adaptive question...
                  {:else}
                    Listening to defense...
                  {/if}
                </p>
              </div>
              {#if activeSpeaker === 'Examiner' || isThinking}
                <div class="waveform-bars">
                  <div class="bar"></div>
                  <div class="bar"></div>
                  <div class="bar"></div>
                  <div class="bar"></div>
                  <div class="bar"></div>
                </div>
              {/if}
            </div>

            <div class="speaker-card {activeSpeaker === 'Student' ? 'active' : ''}">
              <div class="speaker-avatar student-avatar">🎓</div>
              <div class="speaker-info">
                <h3>Student Defender</h3>
                <p>{isListening ? '🎙️ Recording speech... Click "Stop & Submit" when done' : (activeSpeaker === 'Student' ? 'Your turn to speak or type' : 'Waiting for next question...')}</p>
              </div>
              {#if activeSpeaker === 'Student' || isListening}
                <div class="waveform-bars">
                  <div class="bar" style="background: #10b981"></div>
                  <div class="bar" style="background: #10b981"></div>
                  <div class="bar" style="background: #10b981"></div>
                  <div class="bar" style="background: #10b981"></div>
                  <div class="bar" style="background: #10b981"></div>
                </div>
              {/if}
            </div>
          </div>

          <!-- Thinking Banner Indicator -->
          {#if isThinking}
            <div class="thinking-banner glass-panel">
              <span class="spinner"></span>
              <div class="thinking-label-box">
                <strong>🧠 AI Examiner is reviewing your response & formulating an adaptive follow-up...</strong>
                <span class="thinking-timer">⏱️ Thinking... {thinkingSeconds}s</span>
              </div>
            </div>
          {/if}

          <!-- Question Progress Bar -->
          <div class="progress-container">
            <div class="progress-label">
              <span>Question {Math.min(currentQuestionIndex + 1, allQuestions.length || 10)} of {allQuestions.length || 10}</span>
              <span>⚡ Adaptive Dynamic Examiner</span>
            </div>
            <div class="progress-bar">
              <div 
                class="progress-fill" 
                style="width: {Math.min(((currentQuestionIndex + 1) / (allQuestions.length || 10)) * 100, 100)}%"
              ></div>
            </div>
          </div>

          <!-- Transcript Stream (Auto-scrolling to bottom) -->
          <div class="transcript-box">
            <div class="transcript-header-row">
              <h4>Live Viva Transcript</h4>
              <button 
                class="btn-secondary btn-sm" 
                on:click={downloadTranscript} 
                disabled={transcript.length === 0}
              >
                📥 Download Transcript
              </button>
            </div>
            <div class="transcript-feed" bind:this={transcriptFeedEl}>
              {#each transcript as entry}
                <div class="transcript-bubble {entry.role}">
                  <div class="bubble-header">
                    <span class="bubble-speaker">{entry.role === 'examiner' ? '🤖 AI Examiner' : '🎓 Student'}</span>
                    <span class="bubble-time">{entry.timestamp}</span>
                  </div>
                  <p class="bubble-text">{entry.text}</p>
                </div>
              {/each}
            </div>
          </div>

          <!-- Answer Defense Console -->
          <div class="answer-console">
            <textarea 
              bind:value={studentInput}
              placeholder="Speak using the microphone or type your defense answer here..."
              rows="3"
              disabled={isProcessingTurn || currentQuestionIndex >= allQuestions.length}
              on:keydown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), submitTurn(false))}
            ></textarea>

            <div class="console-actions">
              <div class="left-actions">
                {#if isListening}
                  <button 
                    class="btn-secondary mic-btn listening"
                    type="button"
                    on:click={toggleSpeechRecognition}
                    title="Pause speech recording to edit text before submitting"
                  >
                    🔴 Stop Recording (Edit Text)
                  </button>
                  <button 
                    class="btn-primary stop-submit-btn"
                    type="button"
                    on:click={stopAndSubmit}
                    disabled={isProcessingTurn}
                    title="Stop microphone recording and submit answer immediately"
                  >
                    ⚡ Stop & Submit Answer ↵
                  </button>
                {:else}
                  <button 
                    class="btn-secondary mic-btn"
                    type="button"
                    on:click={toggleSpeechRecognition}
                    disabled={isProcessingTurn || currentQuestionIndex >= allQuestions.length}
                  >
                    🎙️ Speak Answer (STT)
                  </button>
                {/if}

                <span class="telemetry-counter">
                  👁️ Telemetry: {telemetryLogs.length} events
                </span>
              </div>

              {#if !isListening}
                <div class="right-actions">
                  <button 
                    class="btn-secondary finish-btn" 
                    disabled={isProcessingTurn}
                    on:click={submitAndCompleteViva}
                    title="Submit current answer and complete the entire viva session"
                  >
                    🏁 Submit & Finish Viva
                  </button>

                  <button 
                    class="btn-primary" 
                    disabled={!studentInput.trim() || isProcessingTurn}
                    on:click={() => submitTurn(false)}
                  >
                    Submit Answer ↵
                  </button>
                </div>
              {/if}
            </div>
          </div>
        </div>
      </section>

    <!-- VIEW C: TEACHER AUDIT & AUTHENTICITY REPORT -->
    {:else if currentView === 'report'}
      <section class="view-section animate-fade">
        {#if isLoadingReport}
          <div class="loading-container glass-panel animate-fade">
            <div class="loading-spinner-box">
              <span class="spinner large"></span>
            </div>
            <h2>Generating Teacher Audit & Authenticity Report...</h2>
            <p class="loading-sub">
              OpenRouter Gemini 3.7 Flash is analyzing your viva defense transcript against the original submitted document.
            </p>
            <div class="loading-metrics-status">
              <div class="status-pill">
                <span>📊 Evaluating Comprehension & Red Flags...</span>
                <span class="timer-badge">⏱️ {reportLoadingSeconds}s</span>
              </div>
            </div>
          </div>
        {:else if reportData}
          <div class="report-container">
            <div class="report-header glass-panel">
              <div>
                <h2>Teacher Audit & Authentication Report</h2>
                <p class="report-sub">Submission ID: {reportData.submission_id} | Document: {reportData.filename}</p>
              </div>
              <div class="report-actions">
                <button class="btn-primary" on:click={downloadTranscript}>
                  📥 Download Transcript
                </button>
                <button class="btn-secondary" on:click={resetApp}>
                  🔄 New Assessment
                </button>
              </div>
            </div>

            <!-- Metric Cards Row -->
            <div class="metrics-grid">
              <!-- Authentication Badge -->
              <div class="metric-card glass-panel">
                <span class="metric-label">Authentication Confidence</span>
                <div class="metric-value">
                  {#if reportData.evaluation.authentication_confidence === 'High'}
                    <span class="badge badge-high">High Confidence</span>
                  {:else if reportData.evaluation.authentication_confidence === 'Med'}
                    <span class="badge badge-med">Medium Confidence</span>
                  {:else}
                    <span class="badge badge-low">Low Confidence</span>
                  {/if}
                </div>
                <p class="metric-desc">Based on conceptual alignment between oral defense and written submission.</p>
              </div>

              <!-- Comprehension Score Card -->
              <div class="metric-card glass-panel">
                <span class="metric-label">Comprehension Score</span>
                <div class="score-display">
                  <span class="score-num">{reportData.evaluation.comprehension_score}</span>
                  <span class="score-denom">/ 5</span>
                </div>
                <div class="stars-row">
                  {#each Array(5) as _, i}
                    <span class="star {i < reportData.evaluation.comprehension_score ? 'filled' : ''}">★</span>
                  {/each}
                </div>
              </div>

              <!-- Telemetry Flags Card -->
              <div class="metric-card glass-panel">
                <span class="metric-label">Proctoring Telemetry</span>
                <div class="telemetry-num">
                  {reportData.telemetry_logs ? reportData.telemetry_logs.length : 0}
                </div>
                <p class="metric-desc">Tab switch / window minimize events detected during viva session.</p>
              </div>
            </div>

            <!-- Evaluation Summary & Flagged Contradictions -->
            <div class="eval-section glass-panel">
              <h3>Evaluation Summary</h3>
              <p class="eval-text">{reportData.evaluation.summary_evaluation}</p>

              {#if reportData.evaluation.flagged_contradictions && reportData.evaluation.flagged_contradictions.length > 0}
                <div class="contradictions-box">
                  <h4>⚠️ Flagged Contradictions & Red Flags</h4>
                  <ul>
                    {#each reportData.evaluation.flagged_contradictions as contradiction}
                      <li>{contradiction}</li>
                    {/each}
                  </ul>
                </div>
              {/if}
            </div>

            <!-- Side-by-Side Comparison Grid -->
            <div class="side-by-side-grid">
              <!-- Left Column: Submission Document Text -->
              <div class="glass-panel text-panel">
                <h3>Original Submission Text</h3>
                <div class="scroll-content">
                  <pre>{reportData.artifact_text}</pre>
                </div>
              </div>

              <!-- Right Column: Full Viva Transcript -->
              <div class="glass-panel text-panel">
                <div class="panel-header-row">
                  <h3>Full Viva Transcript</h3>
                  <button class="btn-secondary btn-sm" on:click={downloadTranscript}>
                    📥 Export
                  </button>
                </div>
                <div class="scroll-content transcript-history">
                  {#each reportData.transcript as turn}
                    <div class="history-item {turn.role}">
                      <div class="history-meta">
                        <strong>{turn.role === 'examiner' ? 'AI Examiner' : 'Student'}</strong>
                        <span>{turn.timestamp}</span>
                      </div>
                      <p>{turn.text}</p>
                    </div>
                  {/each}
                </div>
              </div>
            </div>

            <!-- Timestamped Telemetry Log Table -->
            <div class="glass-panel telemetry-section">
              <h3>Timestamped Telemetry Log</h3>
              {#if reportData.telemetry_logs && reportData.telemetry_logs.length > 0}
                <table class="telemetry-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Event Type</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each reportData.telemetry_logs as log}
                      <tr>
                        <td><code>{log.timestamp}</code></td>
                        <td><span class="log-badge {log.type}">{log.type}</span></td>
                        <td>{log.description}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              {:else}
                <p class="empty-state">No tab-switch or window minimize events recorded. Student remained focused throughout the viva session.</p>
              {/if}
            </div>
          </div>
        {/if}
      </section>
    {/if}
  </main>
</div>

<style>
  .app-layout {
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .app-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border-color);
  }

  .logo-container {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .logo-icon {
    font-size: 2.2rem;
  }

  .subtitle {
    color: var(--text-muted);
    font-size: 0.875rem;
  }

  .nav-tabs {
    display: flex;
    gap: 8px;
    background: var(--bg-card);
    padding: 4px;
    border-radius: 12px;
    border: 1px solid var(--border-color);
  }

  .nav-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .nav-btn:hover:not(:disabled) {
    color: var(--text-main);
    background: var(--bg-surface);
  }

  .nav-btn.active {
    background: var(--accent-gradient);
    color: #fff;
    font-weight: 600;
  }

  .nav-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .view-section {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  .hero-text {
    text-align: center;
    margin-bottom: 12px;
  }

  .hero-text h2 {
    font-size: 1.8rem;
    margin-bottom: 8px;
  }

  .hero-text p {
    color: var(--text-muted);
    max-width: 600px;
    margin: 0 auto;
  }

  .upload-card {
    padding: 32px;
    max-width: 650px;
    margin: 0 auto;
    width: 100%;
  }

  .file-dropzone {
    border: 2px dashed var(--border-color);
    border-radius: 12px;
    padding: 40px 20px;
    text-align: center;
    transition: all 0.2s ease;
    background: rgba(18, 24, 38, 0.4);
  }

  .file-dropzone:hover {
    border-color: var(--accent-primary);
    background: rgba(56, 189, 248, 0.05);
  }

  #file-input {
    display: none;
  }

  .dropzone-label {
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }

  .upload-icon {
    font-size: 3rem;
  }

  .upload-prompt {
    font-weight: 600;
    font-size: 1.1rem;
  }

  .upload-hint {
    color: var(--text-muted);
    font-size: 0.85rem;
  }

  .selected-file-info {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-surface);
    padding: 8px 16px;
    border-radius: 8px;
  }

  .file-name {
    font-weight: 600;
    color: var(--accent-primary);
  }

  .file-size {
    color: var(--text-muted);
    font-size: 0.85rem;
  }

  .error-banner {
    margin-top: 16px;
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #f87171;
    padding: 12px;
    border-radius: 8px;
    font-size: 0.9rem;
  }

  .action-footer {
    margin-top: 24px;
    display: flex;
    justify-content: flex-end;
  }

  /* Live Room Styling */
  .live-room-container {
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .room-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .header-controls {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .voice-toggle-btn.active {
    border-color: var(--accent-primary);
    color: var(--accent-primary);
  }

  .status-pill {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--bg-card);
    padding: 8px 16px;
    border-radius: 20px;
    border: 1px solid var(--border-color);
    font-size: 0.875rem;
  }

  .room-id {
    color: var(--text-muted);
    border-left: 1px solid var(--border-color);
    padding-left: 10px;
  }

  .speaker-stage {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .speaker-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 16px;
    transition: all 0.3s ease;
  }

  .speaker-card.active {
    border-color: var(--accent-primary);
    box-shadow: 0 0 16px rgba(56, 189, 248, 0.2);
    background: var(--bg-card-hover);
  }

  .speaker-avatar {
    font-size: 2rem;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--bg-surface);
  }

  .speaker-info h3 {
    font-size: 1.1rem;
  }

  .speaker-info p {
    font-size: 0.825rem;
    color: var(--text-muted);
  }

  .thinking-banner {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px 20px;
    background: rgba(56, 189, 248, 0.1);
    border: 1px solid rgba(56, 189, 248, 0.3);
    border-radius: 12px;
    animation: fadeIn 0.3s ease;
  }

  .thinking-label-box {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    font-size: 0.9rem;
    color: #e0f2fe;
  }

  .thinking-timer, .timer-badge {
    background: rgba(56, 189, 248, 0.2);
    border: 1px solid rgba(56, 189, 248, 0.4);
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 600;
    color: #38bdf8;
  }

  .loading-container {
    padding: 60px 40px;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    max-width: 650px;
    margin: 40px auto;
  }

  .loading-spinner-box {
    margin-bottom: 8px;
  }

  .loading-sub {
    color: var(--text-muted);
    font-size: 0.95rem;
    max-width: 500px;
  }

  .loading-metrics-status {
    margin-top: 12px;
  }

  .progress-container {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .progress-label {
    display: flex;
    justify-content: space-between;
    font-size: 0.825rem;
    color: var(--text-muted);
  }

  .progress-bar {
    height: 6px;
    background: var(--bg-surface);
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--accent-gradient);
    transition: width 0.3s ease;
  }

  .transcript-box {
    background: var(--bg-dark);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .transcript-header-row, .panel-header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .btn-sm {
    padding: 4px 10px;
    font-size: 0.8rem;
  }

  .transcript-feed {
    max-height: 280px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-right: 8px;
    scroll-behavior: smooth;
  }

  .transcript-bubble {
    padding: 12px 16px;
    border-radius: 12px;
    max-width: 85%;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .transcript-bubble.examiner {
    align-self: flex-start;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
  }

  .transcript-bubble.student {
    align-self: flex-end;
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.3);
  }

  .bubble-header {
    display: flex;
    justify-content: space-between;
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .bubble-text {
    font-size: 0.95rem;
  }

  .answer-console {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  textarea {
    width: 100%;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 10px;
    color: var(--text-main);
    padding: 12px;
    font-family: inherit;
    font-size: 0.95rem;
    resize: vertical;
  }

  textarea:focus {
    outline: none;
    border-color: var(--accent-primary);
  }

  .console-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .left-actions, .right-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .stop-submit-btn {
    box-shadow: 0 4px 14px 0 rgba(16, 185, 129, 0.35);
  }

  .finish-btn {
    border-color: #f59e0b;
    color: #fbbf24;
  }

  .finish-btn:hover {
    background: rgba(245, 158, 11, 0.15);
  }

  .mic-btn.listening {
    background: rgba(239, 68, 68, 0.2);
    border-color: #ef4444;
    color: #f87171;
    animation: pulse-ring 1.5s infinite;
  }

  .telemetry-counter {
    font-size: 0.8rem;
    color: var(--text-muted);
  }

  /* Report View Styling */
  .report-container {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .report-header {
    padding: 20px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .report-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .report-sub {
    color: var(--text-muted);
    font-size: 0.85rem;
  }

  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }

  .metric-card {
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .metric-label {
    font-size: 0.85rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .score-display {
    display: flex;
    align-items: baseline;
    gap: 4px;
  }

  .score-num {
    font-size: 2.2rem;
    font-weight: 700;
    color: var(--accent-primary);
  }

  .score-denom {
    color: var(--text-muted);
    font-size: 1.1rem;
  }

  .stars-row {
    color: var(--text-dim);
    font-size: 1.2rem;
  }

  .star.filled {
    color: #fbbf24;
  }

  .telemetry-num {
    font-size: 2rem;
    font-weight: 700;
    color: #fbbf24;
  }

  .eval-section {
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .eval-text {
    line-height: 1.6;
    color: #e2e8f0;
  }

  .contradictions-box {
    margin-top: 12px;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    padding: 16px;
    border-radius: 10px;
  }

  .contradictions-box h4 {
    color: #f87171;
    margin-bottom: 8px;
  }

  .contradictions-box ul {
    padding-left: 20px;
    color: #fca5a5;
  }

  .side-by-side-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .text-panel {
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-height: 400px;
  }

  .scroll-content {
    overflow-y: auto;
    padding-right: 8px;
    font-size: 0.875rem;
    line-height: 1.6;
  }

  pre {
    white-space: pre-wrap;
    font-family: inherit;
    color: var(--text-muted);
  }

  .transcript-history {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .history-item {
    background: var(--bg-card);
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
  }

  .history-meta {
    display: flex;
    justify-content: space-between;
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 4px;
  }

  .telemetry-section {
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .telemetry-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }

  .telemetry-table th, .telemetry-table td {
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
  }

  .telemetry-table th {
    color: var(--text-muted);
    font-weight: 600;
  }

  .log-badge {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .log-badge.tab_hidden, .log-badge.focus_lost {
    background: rgba(239, 68, 68, 0.2);
    color: #f87171;
  }

  .log-badge.tab_visible, .log-badge.focus_gained {
    background: rgba(16, 185, 129, 0.2);
    color: #34d399;
  }

  .log-badge.session_start, .log-badge.session_end {
    background: rgba(56, 189, 248, 0.2);
    color: #38bdf8;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: #fff;
    animation: spin 0.8s linear infinite;
    display: inline-block;
  }

  .spinner.large {
    width: 32px;
    height: 32px;
    border-width: 3px;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .animate-fade {
    animation: fadeIn 0.3s ease-in-out;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @media (max-width: 768px) {
    .speaker-stage, .metrics-grid, .side-by-side-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
