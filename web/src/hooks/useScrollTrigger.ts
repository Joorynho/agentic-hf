import { useEffect, useCallback, useState } from 'react'

export interface UseScrollTriggerOptions {
  onScroll?: (scrollY: number) => void
  threshold?: number
}

export function useScrollTrigger({ onScroll, threshold = 10 }: UseScrollTriggerOptions = {}) {
  const [scrollY, setScrollY] = useState(0)
  const [isScrolling, setIsScrolling] = useState(false)

  const handleScroll = useCallback(() => {
    const y = window.scrollY
    setScrollY(y)
    setIsScrolling(y > threshold)

    if (onScroll) {
      onScroll(y)
    }
  }, [threshold, onScroll])

  useEffect(() => {
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [handleScroll])

  return {
    scrollY,
    isScrolling,
  }
}
