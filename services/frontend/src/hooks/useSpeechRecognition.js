import { useState, useEffect, useCallback, useRef } from 'react'

/**
 * Custom hook for WebSpeech API voice recognition
 * Detects voice commands for golf swing analyzer controls
 * 
 * Supported commands:
 * - "Ready" or "Calibrate" → triggers calibration
 * - "Axes on" or "Axis on" → enables axes display
 * - "Axes off" or "Axis off" → disables axes display
 * - "Reset" → resets the system
 */
export function useSpeechRecognition({ onCalibrate, onAxesOn, onAxesOff, onReset }) {
  const [isListening, setIsListening] = useState(false)
  const [isSupported, setIsSupported] = useState(false)
  const [lastCommand, setLastCommand] = useState(null)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState(null)
  
  const recognitionRef = useRef(null)
  const commandTimeoutRef = useRef(null)
  const isListeningRef = useRef(false)
  
  // Use refs for callbacks to avoid stale closures
  const callbacksRef = useRef({ onCalibrate, onAxesOn, onAxesOff, onReset })
  
  // Update refs when callbacks change
  useEffect(() => {
    callbacksRef.current = { onCalibrate, onAxesOn, onAxesOff, onReset }
  }, [onCalibrate, onAxesOn, onAxesOff, onReset])

  // Check browser support on mount
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SpeechRecognition) {
      setIsSupported(true)
    } else {
      setIsSupported(false)
      setError('Speech recognition not supported in this browser')
    }
  }, [])

  // Process transcript for commands
  const processCommand = useCallback((text) => {
    const lowerText = text.toLowerCase().trim()
    console.log('Processing voice command:', lowerText)
    
    // Check for calibrate commands
    if (lowerText.includes('ready') || lowerText.includes('calibrate')) {
      setLastCommand('calibrate')
      console.log('Voice: Calibrate command detected')
      callbacksRef.current.onCalibrate?.()
      // Clear command display after 2 seconds
      if (commandTimeoutRef.current) {
        clearTimeout(commandTimeoutRef.current)
      }
      commandTimeoutRef.current = setTimeout(() => setLastCommand(null), 2000)
      return true
    }
    
    // Check for axes on commands
    if (lowerText.includes('axes on') || lowerText.includes('axis on') || 
        lowerText.includes('access on') || lowerText.includes('show axes')) {
      setLastCommand('axes_on')
      console.log('Voice: Axes ON command detected')
      callbacksRef.current.onAxesOn?.()
      if (commandTimeoutRef.current) {
        clearTimeout(commandTimeoutRef.current)
      }
      commandTimeoutRef.current = setTimeout(() => setLastCommand(null), 2000)
      return true
    }
    
    // Check for axes off commands
    if (lowerText.includes('axes off') || lowerText.includes('axis off') || 
        lowerText.includes('access off') || lowerText.includes('hide axes')) {
      setLastCommand('axes_off')
      console.log('Voice: Axes OFF command detected')
      callbacksRef.current.onAxesOff?.()
      if (commandTimeoutRef.current) {
        clearTimeout(commandTimeoutRef.current)
      }
      commandTimeoutRef.current = setTimeout(() => setLastCommand(null), 2000)
      return true
    }
    
    // Check for reset command
    if (lowerText.includes('reset')) {
      setLastCommand('reset')
      console.log('Voice: Reset command detected')
      callbacksRef.current.onReset?.()
      if (commandTimeoutRef.current) {
        clearTimeout(commandTimeoutRef.current)
      }
      commandTimeoutRef.current = setTimeout(() => setLastCommand(null), 2000)
      return true
    }
    
    return false
  }, [])

  // Start listening
  const startListening = useCallback(() => {
    if (!isSupported) {
      setError('Speech recognition not supported')
      return
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    const recognition = new SpeechRecognition()
    
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    
    recognition.onstart = () => {
      setIsListening(true)
      isListeningRef.current = true
      setError(null)
      console.log('Speech recognition started')
    }
    
    recognition.onresult = (event) => {
      let finalTranscript = ''
      let interimTranscript = ''
      
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          finalTranscript += transcript
        } else {
          interimTranscript += transcript
        }
      }
      
      // Update display transcript
      const displayText = finalTranscript || interimTranscript
      setTranscript(displayText)
      
      // Process final results for commands
      if (finalTranscript) {
        processCommand(finalTranscript)
      }
    }
    
    recognition.onerror = (event) => {
      // Don't treat "no-speech" as an error, just keep listening
      if (event.error === 'no-speech') {
        return
      }
      
      console.error('Speech recognition error:', event.error)
      setError(`Speech recognition error: ${event.error}`)
      setIsListening(false)
      isListeningRef.current = false
    }
    
    recognition.onend = () => {
      console.log('Speech recognition ended, isListening:', isListeningRef.current)
      // Auto-restart if we're supposed to be listening (use ref for current value)
      if (isListeningRef.current) {
        try {
          console.log('Restarting speech recognition...')
          recognition.start()
        } catch (e) {
          console.log('Failed to restart:', e)
          // Ignore errors on restart
        }
      } else {
        setIsListening(false)
      }
    }
    
    recognitionRef.current = recognition
    
    try {
      recognition.start()
    } catch (e) {
      setError('Failed to start speech recognition')
    }
  }, [isSupported, processCommand])

  // Stop listening
  const stopListening = useCallback(() => {
    console.log('Stopping speech recognition')
    isListeningRef.current = false
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      recognitionRef.current = null
    }
    setIsListening(false)
    setTranscript('')
  }, [])

  // Toggle listening
  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening()
    } else {
      startListening()
    }
  }, [isListening, startListening, stopListening])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop()
      }
      if (commandTimeoutRef.current) {
        clearTimeout(commandTimeoutRef.current)
      }
    }
  }, [])

  return {
    isListening,
    isSupported,
    lastCommand,
    transcript,
    error,
    startListening,
    stopListening,
    toggleListening,
  }
}
