import { useMarkerWebSocket } from '../hooks/useMarkerWebSocket'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'

function Dashboard() {
  const { 
    connectionStatus, 
    markerData, 
    lastMessageTime,
    impactData,
    calibrate,
    reset,
    clearImpact,
    toggleAxes,
    setShowAxes
  } = useMarkerWebSocket()

  // Get axes visibility state from backend
  let showAxes = markerData?.show_axes ?? true

  // Speech recognition for voice commands
  const {
    isListening,
    isSupported: isSpeechSupported,
    lastCommand,
    transcript,
    toggleListening,
  } = useSpeechRecognition({
    onCalibrate: calibrate,
    onAxesOn: () => setShowAxes(true),
    onAxesOff: () => setShowAxes(false),
    onReset: reset,
  })

  // Determine tracking status from marker data
  let isTracking = false
  if (markerData && markerData.status === 'tracking') {
    isTracking = true
  }

  // Get current state
  let currentState = markerData?.state || 'idle'
  let calibrationProgress = markerData?.calibration_progress || 0
  let metrics = markerData?.metrics || null

  // Format time for display
  let formattedTime = ''
  if (lastMessageTime) {
    formattedTime = lastMessageTime.toLocaleTimeString()
  }

  // Determine if ready to swing
  let isReady = currentState === 'ready'
  let needsCalibration = currentState === 'idle'
  let isCalibrating = currentState === 'calibrating'
  let swingDetected = currentState === 'swing_detected'

  return (
    <div className="min-h-screen p-4 md:p-8 lg:p-12">
      {/* Header */}
      <header className="mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-1 tracking-tight">
            Golf Swing Analyzer
          </h1>
          <p className="text-gray-400 text-base md:text-lg">
            6-DOF ArUco marker tracking system
          </p>
        </div>
        
        {/* Control Buttons */}
        <div className="flex gap-3 flex-wrap items-center">
          {/* Voice Control Button */}
          {isSpeechSupported && (
            <MicrophoneButton
              isListening={isListening}
              onClick={toggleListening}
              lastCommand={lastCommand}
              transcript={transcript}
            />
          )}
          <button
            onClick={calibrate}
            disabled={connectionStatus !== 'connected' || isCalibrating}
            className={`px-6 py-3 rounded-xl font-semibold text-sm uppercase tracking-wider transition-all duration-200 ${
              needsCalibration
                ? 'bg-yellow-500 hover:bg-yellow-400 text-black shadow-lg shadow-yellow-500/30'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-500/30'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {isCalibrating ? `Calibrating ${Math.round(calibrationProgress * 100)}%` : 'Calibrate'}
          </button>
          <button
            onClick={reset}
            disabled={connectionStatus !== 'connected'}
            className="px-6 py-3 rounded-xl font-semibold text-sm uppercase tracking-wider bg-gray-700 hover:bg-gray-600 text-white transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Reset
          </button>
          <button
            onClick={toggleAxes}
            disabled={connectionStatus !== 'connected'}
            className={`px-4 py-3 rounded-xl font-semibold text-sm uppercase tracking-wider transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
              showAxes
                ? 'bg-blue-600 hover:bg-blue-500 text-white'
                : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
            }`}
            title="Toggle XYZ axes display on video"
          >
            {showAxes ? 'Axes ON' : 'Axes OFF'}
          </button>
        </div>
      </header>

      {/* Status Banner */}
      <StatusBanner 
        isConnected={connectionStatus === 'connected'}
        isReady={isReady}
        needsCalibration={needsCalibration}
        isCalibrating={isCalibrating}
        swingDetected={swingDetected}
        isTracking={isTracking}
      />

      {/* Main Metrics Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 mt-8">
        {/* Face Angle Gauge */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-6 border border-gray-700/50 shadow-xl">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Face Angle
          </h2>
          <FaceAngleGauge 
            value={metrics?.face_angle || 0} 
            isActive={isReady && isTracking}
          />
        </div>

        {/* Club Path Indicator */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-6 border border-gray-700/50 shadow-xl">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Club Path
          </h2>
          <ClubPathIndicator 
            value={metrics?.club_path || 0}
            isActive={isReady && isTracking}
          />
        </div>

        {/* Attack Angle */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-6 border border-gray-700/50 shadow-xl">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Attack Angle
          </h2>
          <AttackAngleDisplay 
            value={metrics?.attack_angle || 0}
            isActive={isReady && isTracking}
          />
        </div>
      </div>

      {/* Impact Results Card */}
      {impactData && (
        <div className="mt-8">
          <ImpactResultsCard data={impactData} onClear={clearImpact} />
        </div>
      )}

      {/* Connection & Debug Info */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4 mt-8">
        {/* Connection Status */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-5 border border-gray-700/50 shadow-xl">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Connection
          </h2>
          <div className="flex items-center gap-3">
            <ConnectionIndicator status={connectionStatus} />
            <span className="text-white font-medium capitalize text-sm">
              {connectionStatus}
            </span>
          </div>
        </div>

        {/* Tracking Status */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-5 border border-gray-700/50 shadow-xl">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Tracking
          </h2>
          <div className="flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${isTracking ? 'bg-emerald-500 animate-pulse' : 'bg-gray-500'}`} />
            <span className={`font-medium text-sm ${isTracking ? 'text-emerald-400' : 'text-gray-400'}`}>
              {isTracking ? 'Active' : 'No Marker'}
            </span>
          </div>
        </div>

        {/* Last Update */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-5 border border-gray-700/50 shadow-xl">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Last Update
          </h2>
          <p className="text-lg font-mono text-white">
            {formattedTime || '—'}
          </p>
        </div>

        {/* Lie Angle */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-5 border border-gray-700/50 shadow-xl">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Lie Angle
          </h2>
          <p className={`text-2xl font-mono ${isReady && isTracking ? 'text-white' : 'text-gray-500'}`}>
            {isReady && isTracking ? `${(metrics?.lie_angle || 0).toFixed(1)}°` : '—'}
          </p>
        </div>
      </div>

      {/* Raw Data (Collapsible) */}
      <details className="mt-8" open>
        <summary className="cursor-pointer text-gray-500 hover:text-gray-300 text-sm font-medium mb-4">
          Debug Info
        </summary>
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-6 border border-gray-700/50 shadow-xl">
          {/* Debug Message */}
          {markerData?.debug && (
            <div className="mb-4 p-4 bg-gray-900/50 rounded-xl">
              <p className="text-yellow-400 font-mono text-sm mb-2">
                {markerData.debug.message}
              </p>
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-gray-500">Markers Found:</span>
                  <span className={`ml-2 ${markerData.debug.num_markers >= 2 ? 'text-emerald-400' : markerData.debug.num_markers === 1 ? 'text-yellow-400' : 'text-red-400'}`}>
                    {markerData.debug.num_markers || 0} {markerData.debug.num_markers >= 2 ? '✓' : markerData.debug.num_markers === 1 ? '(need 2 for best accuracy)' : ''}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Marker IDs:</span>
                  <span className={`ml-2 ${markerData.debug.markers_found?.length > 0 ? 'text-emerald-400' : 'text-gray-500'}`}>
                    {JSON.stringify(markerData.debug.markers_found) || '[]'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Pose Estimated:</span>
                  <span className={`ml-2 ${markerData.debug.pose_estimated ? 'text-emerald-400' : 'text-red-400'}`}>
                    {markerData.debug.pose_estimated ? 'Yes ✓' : 'No'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Calibration:</span>
                  <span className="ml-2 text-white">
                    {Math.round((markerData.calibration_progress || 0) * 100)}%
                  </span>
                </div>
              </div>
            </div>
          )}
          <pre className="text-emerald-400 text-xs leading-relaxed overflow-auto max-h-64 font-mono">
            {JSON.stringify(markerData, null, 2)}
          </pre>
        </div>
      </details>
    </div>
  )
}

// =============================================================================
// STATUS BANNER
// =============================================================================

function StatusBanner({ isConnected, isReady, needsCalibration, isCalibrating, swingDetected, isTracking }) {
  if (!isConnected) {
    return (
      <div className="bg-gray-700/50 rounded-2xl p-4 border border-gray-600/50 flex items-center gap-4">
        <div className="w-3 h-3 rounded-full bg-gray-500" />
        <span className="text-gray-400 font-medium">Connecting to backend...</span>
      </div>
    )
  }

  if (isCalibrating) {
    return (
      <div className="bg-yellow-500/10 rounded-2xl p-4 border border-yellow-500/30 flex items-center gap-4">
        <div className="w-3 h-3 rounded-full bg-yellow-500 animate-pulse" />
        <span className="text-yellow-400 font-medium">Hold club at address position...</span>
      </div>
    )
  }

  if (needsCalibration) {
    return (
      <div className="bg-yellow-500/10 rounded-2xl p-4 border border-yellow-500/30 flex items-center gap-4">
        <div className="w-3 h-3 rounded-full bg-yellow-500" />
        <span className="text-yellow-400 font-medium">Calibrate First — Set address position before swinging</span>
      </div>
    )
  }

  if (swingDetected) {
    return (
      <div className="bg-purple-500/10 rounded-2xl p-4 border border-purple-500/30 flex items-center gap-4">
        <div className="w-3 h-3 rounded-full bg-purple-500 animate-pulse" />
        <span className="text-purple-400 font-medium">Swing Detected! Review impact data below.</span>
      </div>
    )
  }

  if (isReady && isTracking) {
    return (
      <div className="bg-emerald-500/10 rounded-2xl p-4 border border-emerald-500/30 flex items-center gap-4">
        <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse shadow-lg shadow-emerald-500/50" />
        <span className="text-emerald-400 font-medium">Ready to Swing</span>
      </div>
    )
  }

  if (isReady) {
    return (
      <div className="bg-blue-500/10 rounded-2xl p-4 border border-blue-500/30 flex items-center gap-4">
        <div className="w-3 h-3 rounded-full bg-blue-500" />
        <span className="text-blue-400 font-medium">Calibrated — Position marker in frame</span>
      </div>
    )
  }

  return null
}

// =============================================================================
// MICROPHONE BUTTON (Voice Control)
// =============================================================================

function MicrophoneButton({ isListening, onClick, lastCommand, transcript }) {
  // Map command to display text
  let commandDisplay = ''
  if (lastCommand === 'calibrate') {
    commandDisplay = 'Calibrating...'
  } else if (lastCommand === 'axes_on') {
    commandDisplay = 'Axes ON'
  } else if (lastCommand === 'axes_off') {
    commandDisplay = 'Axes OFF'
  } else if (lastCommand === 'reset') {
    commandDisplay = 'Reset'
  }

  return (
    <div className="flex items-center gap-2">
      {/* Listening indicator - to the left of button */}
      {isListening && (
        <div className="flex items-center gap-2 mr-1">
          {/* Command feedback or transcript */}
          {lastCommand ? (
            <span className="px-2 py-1 rounded-lg bg-emerald-500/20 text-emerald-400 text-xs font-medium border border-emerald-500/30">
              ✓ {commandDisplay}
            </span>
          ) : transcript ? (
            <span className="px-2 py-1 rounded-lg bg-gray-700/80 text-gray-300 text-xs max-w-[120px] truncate">
              "{transcript}"
            </span>
          ) : null}
          
          {/* Sound wave animation - slower */}
          <div className="flex items-center gap-0.5">
            <span className="w-1 h-3 bg-pink-500 rounded-full animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '0ms' }} />
            <span className="w-1 h-5 bg-pink-500 rounded-full animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '150ms' }} />
            <span className="w-1 h-4 bg-pink-500 rounded-full animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '300ms' }} />
            <span className="w-1 h-6 bg-pink-500 rounded-full animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '450ms' }} />
            <span className="w-1 h-3 bg-pink-500 rounded-full animate-[soundwave_1.2s_ease-in-out_infinite]" style={{ animationDelay: '600ms' }} />
          </div>
        </div>
      )}

      {/* Microphone Button */}
      <button
        onClick={onClick}
        className={`relative p-3 rounded-xl font-semibold text-sm transition-all duration-300 ${
          isListening
            ? 'bg-gradient-to-br from-pink-500 to-rose-600 text-white shadow-lg shadow-pink-500/40 scale-105'
            : 'bg-gray-700 hover:bg-gray-600 text-gray-300 hover:text-white'
        }`}
        title={isListening ? 'Voice control active - Click to stop' : 'Enable voice control'}
      >
        {/* Pulse animation when listening */}
        {isListening && (
          <>
            <span className="absolute inset-0 rounded-xl bg-pink-500 animate-ping opacity-30" />
            <span className="absolute inset-0 rounded-xl bg-pink-500/20 animate-pulse" />
          </>
        )}
        
        {/* Microphone Icon */}
        <svg 
          xmlns="http://www.w3.org/2000/svg" 
          viewBox="0 0 24 24" 
          fill="currentColor" 
          className="w-5 h-5 relative z-10"
        >
          <path d="M8.25 4.5a3.75 3.75 0 117.5 0v8.25a3.75 3.75 0 11-7.5 0V4.5z" />
          <path d="M6 10.5a.75.75 0 01.75.75v1.5a5.25 5.25 0 1010.5 0v-1.5a.75.75 0 011.5 0v1.5a6.751 6.751 0 01-6 6.709v2.291h3a.75.75 0 010 1.5h-7.5a.75.75 0 010-1.5h3v-2.291a6.751 6.751 0 01-6-6.709v-1.5A.75.75 0 016 10.5z" />
        </svg>
      </button>
    </div>
  )
}

// =============================================================================
// FACE ANGLE GAUGE (Semi-circle)
// =============================================================================

function FaceAngleGauge({ value, isActive }) {
  // Clamp value between -30 and +30 degrees for display
  const clampedValue = Math.max(-30, Math.min(30, value))
  
  // Convert to rotation: -30 = -90deg, 0 = 0deg, +30 = +90deg
  const rotation = (clampedValue / 30) * 90
  
  // Determine color based on value
  let color = 'text-emerald-500'
  let label = 'Square'
  
  if (Math.abs(value) > 5) {
    color = 'text-red-500'
    label = value > 0 ? 'Open' : 'Closed'
  } else if (Math.abs(value) > 2) {
    color = 'text-yellow-500'
    label = value > 0 ? 'Slightly Open' : 'Slightly Closed'
  }

  if (!isActive) {
    color = 'text-gray-500'
  }

  return (
    <div className="flex flex-col items-center">
      {/* Gauge SVG */}
      <div className="relative w-48 h-28 mb-4">
        <svg viewBox="0 0 200 110" className="w-full h-full">
          {/* Background arc */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="currentColor"
            strokeWidth="12"
            strokeLinecap="round"
            className="text-gray-700"
          />
          
          {/* Colored segments */}
          {/* Red left (closed) */}
          <path
            d="M 20 100 A 80 80 0 0 1 50 40"
            fill="none"
            stroke="currentColor"
            strokeWidth="12"
            strokeLinecap="round"
            className="text-red-900/50"
          />
          
          {/* Yellow left */}
          <path
            d="M 50 40 A 80 80 0 0 1 85 22"
            fill="none"
            stroke="currentColor"
            strokeWidth="12"
            strokeLinecap="round"
            className="text-yellow-900/50"
          />
          
          {/* Green center */}
          <path
            d="M 85 22 A 80 80 0 0 1 115 22"
            fill="none"
            stroke="currentColor"
            strokeWidth="12"
            strokeLinecap="round"
            className="text-emerald-900/50"
          />
          
          {/* Yellow right */}
          <path
            d="M 115 22 A 80 80 0 0 1 150 40"
            fill="none"
            stroke="currentColor"
            strokeWidth="12"
            strokeLinecap="round"
            className="text-yellow-900/50"
          />
          
          {/* Red right (open) */}
          <path
            d="M 150 40 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="currentColor"
            strokeWidth="12"
            strokeLinecap="round"
            className="text-red-900/50"
          />
          
          {/* Center marker */}
          <line x1="100" y1="100" x2="100" y2="25" stroke="currentColor" strokeWidth="2" className="text-gray-500" />
          
          {/* Needle */}
          <g transform={`rotate(${rotation}, 100, 100)`}>
            <line 
              x1="100" 
              y1="100" 
              x2="100" 
              y2="30" 
              stroke="currentColor" 
              strokeWidth="4" 
              strokeLinecap="round"
              className={isActive ? 'text-white' : 'text-gray-600'}
            />
            <circle cx="100" cy="100" r="8" fill="currentColor" className={isActive ? 'text-white' : 'text-gray-600'} />
          </g>
        </svg>
        
        {/* Labels */}
        <span className="absolute bottom-0 left-2 text-xs text-gray-500">CLOSED</span>
        <span className="absolute bottom-0 right-2 text-xs text-gray-500">OPEN</span>
      </div>
      
      {/* Value Display */}
      <div className="text-center">
        <p className={`text-4xl font-mono font-bold ${color}`}>
          {isActive ? `${value > 0 ? '+' : ''}${value.toFixed(1)}°` : '—'}
        </p>
        <p className={`text-sm mt-1 ${isActive ? color : 'text-gray-500'}`}>
          {isActive ? label : 'Inactive'}
        </p>
      </div>
    </div>
  )
}

// =============================================================================
// CLUB PATH INDICATOR
// =============================================================================

function ClubPathIndicator({ value, isActive }) {
  // value is in cm (positive = out-to-in, negative = in-to-out)
  // Clamp for display
  const clampedValue = Math.max(-10, Math.min(10, value))
  
  let direction = 'Straight'
  let color = 'text-emerald-500'
  
  if (Math.abs(value) > 2) {
    if (value > 0) {
      direction = 'Out-to-In'
      color = 'text-blue-400'
    } else {
      direction = 'In-to-Out'
      color = 'text-orange-400'
    }
  } else if (Math.abs(value) > 0.5) {
    if (value > 0) {
      direction = 'Slight Out-to-In'
      color = 'text-blue-300'
    } else {
      direction = 'Slight In-to-Out'
      color = 'text-orange-300'
    }
  }

  if (!isActive) {
    color = 'text-gray-500'
  }

  // Arrow rotation: negative (in-to-out) points left-ish, positive points right-ish
  const arrowRotation = clampedValue * 9 // 10cm = 90 degrees

  return (
    <div className="flex flex-col items-center">
      {/* Arrow indicator */}
      <div className="relative w-48 h-24 mb-4 flex items-center justify-center">
        {/* Target line */}
        <div className="absolute w-full h-0.5 bg-gray-700" />
        <div className="absolute w-3 h-3 border-t-2 border-r-2 border-gray-500 rotate-45 right-2" />
        
        {/* Direction arrow */}
        <svg 
          viewBox="0 0 100 40" 
          className={`w-32 h-16 transition-transform duration-200 ${isActive ? color : 'text-gray-600'}`}
          style={{ transform: `rotate(${arrowRotation}deg)` }}
        >
          <path
            d="M 10 20 L 70 20 M 55 10 L 70 20 L 55 30"
            fill="none"
            stroke="currentColor"
            strokeWidth="6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      {/* Labels */}
      <div className="w-full flex justify-between text-xs text-gray-500 mb-4">
        <span>IN-OUT</span>
        <span>TARGET</span>
        <span>OUT-IN</span>
      </div>
      
      {/* Value Display */}
      <div className="text-center">
        <p className={`text-3xl font-mono font-bold ${color}`}>
          {isActive ? `${value > 0 ? '+' : ''}${value.toFixed(1)} cm` : '—'}
        </p>
        <p className={`text-sm mt-1 ${isActive ? color : 'text-gray-500'}`}>
          {isActive ? direction : 'Inactive'}
        </p>
      </div>
    </div>
  )
}

// =============================================================================
// ATTACK ANGLE DISPLAY
// =============================================================================

function AttackAngleDisplay({ value, isActive }) {
  // value is in cm (negative = hitting down, positive = hitting up)
  let direction = 'Level'
  let color = 'text-emerald-500'
  let icon = '→'
  
  if (value < -1) {
    direction = 'Descending'
    color = 'text-blue-400'
    icon = '↘'
  } else if (value > 1) {
    direction = 'Ascending'
    color = 'text-orange-400'
    icon = '↗'
  }

  if (!isActive) {
    color = 'text-gray-500'
    icon = '—'
  }

  return (
    <div className="flex flex-col items-center justify-center h-full">
      {/* Large icon */}
      <div className={`text-6xl mb-4 ${color}`}>
        {icon}
      </div>
      
      {/* Value Display */}
      <div className="text-center">
        <p className={`text-4xl font-mono font-bold ${color}`}>
          {isActive ? `${value > 0 ? '+' : ''}${value.toFixed(1)} cm` : '—'}
        </p>
        <p className={`text-sm mt-1 ${isActive ? color : 'text-gray-500'}`}>
          {isActive ? direction : 'Inactive'}
        </p>
      </div>
    </div>
  )
}

// =============================================================================
// IMPACT RESULTS CARD
// =============================================================================

function ImpactResultsCard({ data, onClear }) {
  const impact = data.impact

  return (
    <div className="bg-purple-900/20 backdrop-blur-sm rounded-2xl p-6 border border-purple-500/30 shadow-xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-purple-300 uppercase tracking-wider">
          Impact Results
        </h2>
        <button
          onClick={onClear}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          Clear
        </button>
      </div>
      
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        <div className="text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Face Angle</p>
          <p className="text-3xl font-mono font-bold text-white">
            {impact?.face_angle?.toFixed(1)}°
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Club Path</p>
          <p className="text-3xl font-mono font-bold text-white">
            {(impact?.club_path * 100)?.toFixed(1)} cm
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Attack Angle</p>
          <p className="text-3xl font-mono font-bold text-white">
            {(impact?.attack_angle * 100)?.toFixed(1)} cm
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Lie Angle</p>
          <p className="text-3xl font-mono font-bold text-white">
            {impact?.lie_angle?.toFixed(1)}°
          </p>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// CONNECTION INDICATOR
// =============================================================================

function ConnectionIndicator({ status }) {
  let colorClass = 'bg-gray-500'
  let pulseClass = ''

  if (status === 'connected') {
    colorClass = 'bg-emerald-500'
    pulseClass = 'animate-pulse'
  } else if (status === 'connecting') {
    colorClass = 'bg-yellow-500'
    pulseClass = 'animate-pulse'
  } else if (status === 'error') {
    colorClass = 'bg-red-500'
  }

  return (
    <div className={`w-2.5 h-2.5 rounded-full ${colorClass} ${pulseClass}`} />
  )
}

export default Dashboard
