import { useState, useEffect, useCallback, useRef } from 'react'

const WS_URL = 'ws://localhost:8000/ws'

/**
 * Custom hook to manage WebSocket connection for golf swing analysis
 */
export function useMarkerWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState('disconnected')
  const [markerData, setMarkerData] = useState(null)
  const [lastMessageTime, setLastMessageTime] = useState(null)
  const [impactData, setImpactData] = useState(null)
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    setConnectionStatus('connecting')
    
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionStatus('connected')
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setMarkerData(data)
        setLastMessageTime(new Date())
        
        // Capture impact data separately
        if (data.impact) {
          setImpactData(data.impact)
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err)
      }
    }

    ws.onclose = () => {
      setConnectionStatus('disconnected')
      setMarkerData(null)
      console.log('WebSocket disconnected')
      
      // Auto-reconnect after 2 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        connect()
      }, 2000)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setConnectionStatus('error')
    }
  }, [])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const sendCommand = useCallback((action) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action }))
    }
  }, [])

  const calibrate = useCallback(() => {
    sendCommand('calibrate')
  }, [sendCommand])

  const reset = useCallback(() => {
    sendCommand('reset')
    setImpactData(null)
  }, [sendCommand])

  const clearImpact = useCallback(() => {
    sendCommand('clear_impact')
    setImpactData(null)
  }, [sendCommand])

  const toggleAxes = useCallback(() => {
    sendCommand('toggle_axes')
  }, [sendCommand])

  const setShowAxes = useCallback((value) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'set_axes', value }))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      disconnect()
    }
  }, [connect, disconnect])

  return {
    connectionStatus,
    markerData,
    lastMessageTime,
    impactData,
    reconnect: connect,
    calibrate,
    reset,
    clearImpact,
    toggleAxes,
    setShowAxes,
  }
}
