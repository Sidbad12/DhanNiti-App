import React, { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, LineSeries } from 'lightweight-charts';
import { socketManager } from '../../lib/charting/socket';
import { RoundedCandlestickSeries } from '../../lib/charting/lightweight-plugins/rounded-candles.js';
import { FootprintSeries } from '../../lib/charting/lightweight-plugins/footprint.js';
import VolumeProfile from './VolumeProfile';
import { calculateSMA, calculateEMA, calculateVWAP, calculateBollingerBands } from '../../lib/charting/indicators';

interface CandleChartProps {
  chartId: string;
  symbol: string;
  timeframe: string;
  bucketSize?: number;
  multiplier?: number;
  chartType?: 'candlestick' | 'footprint';
  showVolumeProfile?: boolean;
  indicators?: string[];
  onSelect?: () => void;
  isActive?: boolean;
  onBookUpdate?: (bookData: any) => void;
  disableZoom?: boolean;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

function generateMockHistoricalData(symbol: string, timeframe: string, effectiveBucketSize: number): any[] {
  const data: any[] = [];
  let ltp = symbol.includes('NIFTY') ? 22000.0 : symbol.includes('RELIANCE') ? 2500.0 : symbol.includes('TCS') ? 3400.0 : 800.0;
  const count = 100; // Generate 100 historical bars
  
  const now = new Date();
  for (let i = count; i > 0; i--) {
    const barDate = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    const dateStr = barDate.toISOString().split("T")[0];
    
    const changePercent = (Math.random() - 0.5) * 0.015;
    const open = ltp;
    const close = ltp * (1 + changePercent);
    const high = Math.max(open, close) * (1 + Math.random() * 0.008);
    const low = Math.min(open, close) * (1 - Math.random() * 0.008);
    
    ltp = close;
    
    // Generate footprint cells
    const footprint: any[] = [];
    const lowLevel = Math.floor(low / effectiveBucketSize) * effectiveBucketSize;
    const highLevel = Math.ceil(high / effectiveBucketSize) * effectiveBucketSize;
    
    let cumDelta = 0;
    for (let level = lowLevel; level <= highLevel; level += effectiveBucketSize) {
      const buyVol = Math.floor(Math.random() * 12000) + 1000;
      const sellVol = Math.floor(Math.random() * 12000) + 1000;
      footprint.push({
        priceLevel: Number(level.toFixed(2)),
        buyVolume: buyVol,
        sellVolume: sellVol
      });
      cumDelta += (buyVol - sellVol);
    }
    
    data.push({
      time: dateStr,
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: Math.floor(Math.random() * 500000) + 100000,
      footprint,
      delta: cumDelta,
      cum_delta: cumDelta + (data.length > 0 ? data[data.length - 1].cum_delta : 0)
    });
  }
  
  return data;
}

export default function CandleChart({
  chartId,
  symbol,
  timeframe,
  bucketSize = 0.05,
  multiplier = 100,
  chartType = 'footprint',
  showVolumeProfile = true,
  indicators = [],
  onSelect,
  isActive = false,
  onBookUpdate,
  disableZoom = false,
}: CandleChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<any> | null>(null);
  const footprintSeriesRef = useRef<ISeriesApi<any> | null>(null);
  const indicatorSeriesRefs = useRef<{ [key: string]: any }>({});

  const [chartData, setChartData] = useState<any[]>([]);
  const [legendData, setLegendData] = useState<any>(null);
  const [visibleRange, setVisibleRange] = useState<{ from: number; to: number } | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const effectiveBucketSize = bucketSize * multiplier;

  // 1. Chart initialization
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const width = chartContainerRef.current.clientWidth || 600;
    const height = chartContainerRef.current.clientHeight || 300;
    console.log(`[CandleChart] Initializing chart ${chartId} for ${symbol} with initial size: ${width}x${height}`);

    let chart: IChartApi;
    try {
      // Create chart instance
      chart = createChart(chartContainerRef.current, {
        width,
        height,
        layout: {
          background: { color: '#0d1117' },
          textColor: '#b2b5be',
        },
        grid: {
          vertLines: { color: '#1e2d40' },
          horzLines: { color: '#1e2d40' },
        },
        timeScale: {
          borderColor: '#1e2d40',
          timeVisible: true,
          secondsVisible: false,
          rightOffset: chartType === 'footprint' ? 4 : 10,
        },
        rightPriceScale: {
          borderColor: '#1e2d40',
          autoScale: true,
        },
        crosshair: {
          mode: 0,
          vertLine: { labelVisible: true },
          horzLine: { labelVisible: true },
        },
        handleScale: disableZoom ? {
          mouseWheel: false,
          pinch: false,
          axisPressedMouseMove: false,
        } : true,
        handleScroll: disableZoom ? {
          mouseWheel: false,
          pressedMouseMove: true,
          horzTouchDrag: true,
          vertTouchDrag: false,
        } : true,
      });
      chartRef.current = chart;
    } catch (err) {
      console.error('[CandleChart] Failed to createChart:', err);
      return;
    }

    let candleSeries: any = null;
    let footprintSeries: any = null;

    try {
      // Add custom Rounded Candlestick Series
      candleSeries = chart.addCustomSeries((RoundedCandlestickSeries as any).create(), {
        upColor: '#00d97e',
        downColor: '#ff4d6a',
        borderUpColor: '#00d97e',
        borderDownColor: '#ff4d6a',
        wickUpColor: '#00d97e',
        wickDownColor: '#ff4d6a',
        borderRadius: 3,
        borderVisible: true,
        wickVisible: true,
        visible: chartType === 'candlestick',
      } as any);
      candleSeriesRef.current = candleSeries;
    } catch (err) {
      console.error('[CandleChart] Failed to add custom rounded candlestick series:', err);
    }

    try {
      // Add custom Footprint Series
      footprintSeries = chart.addCustomSeries((FootprintSeries as any).create(), {
        upColor: '#00d97e',
        downColor: '#ff4d6a',
        borderUpColor: '#00d97e',
        borderDownColor: '#ff4d6a',
        wickUpColor: '#00d97e',
        wickDownColor: '#ff4d6a',
        tickSize: effectiveBucketSize,
        visible: chartType === 'footprint',
      } as any);
      footprintSeriesRef.current = footprintSeries;
    } catch (err) {
      console.error('[CandleChart] Failed to add custom footprint series:', err);
    }

    // Handle crosshair moves for legend updating
    chart.subscribeCrosshairMove((param) => {
      if (param.time) {
        const seriesData = (candleSeries && param.seriesData.get(candleSeries)) || (footprintSeries && param.seriesData.get(footprintSeries));
        if (seriesData) {
          setLegendData(seriesData);
        }
      } else {
        // Reset to last data point
        setLegendData(null);
      }
    });

    // Handle visible range changes
    chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
      if (range) {
        setVisibleRange({
          from: typeof range.from === 'number' ? range.from : (range.from as any).timestamp ?? 0,
          to: typeof range.to === 'number' ? range.to : (range.to as any).timestamp ?? 0,
        });
      }
    });

    // Resize observer to handle dynamic layout / tab changes and fade animations
    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0 || !chartRef.current) return;
      const { width: newWidth, height: newHeight } = entries[0].contentRect;
      console.log(`[CandleChart] ResizeObserver triggered for ${chartId} / ${symbol}: ${newWidth}x${newHeight}`);
      if (newWidth > 0 && newHeight > 0) {
        chart.applyOptions({ width: newWidth, height: newHeight });
      }
    });

    if (chartContainerRef.current) {
      resizeObserver.observe(chartContainerRef.current);
    }

    // Handle window resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        const w = chartContainerRef.current.clientWidth || 600;
        const h = chartContainerRef.current.clientHeight || 300;
        chart.applyOptions({
          width: w,
          height: h,
        });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  // 2. Adjust visibility options when chartType changes
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current || !footprintSeriesRef.current) return;

    candleSeriesRef.current.applyOptions({ visible: chartType === 'candlestick' });
    footprintSeriesRef.current.applyOptions({ visible: chartType === 'footprint' });

    const rightOffset = chartType === 'footprint' ? 4 : 10;
    chartRef.current.applyOptions({ timeScale: { rightOffset } });
  }, [chartType]);

  // 3. Setup Indicators
  useEffect(() => {
    if (!chartRef.current || !chartData || chartData.length === 0) return;

    const chart = chartRef.current;
    const activeIndicators = indicators || [];

    // Remove inactive indicators
    Object.keys(indicatorSeriesRefs.current).forEach((key) => {
      if (!activeIndicators.includes(key) && !key.startsWith('BB_') && key !== 'BB') {
        chart.removeSeries(indicatorSeriesRefs.current[key]);
        delete indicatorSeriesRefs.current[key];
      }
    });

    // Special handling for BB cleanup
    if (!activeIndicators.includes('BB') && indicatorSeriesRefs.current['BB']) {
      if (indicatorSeriesRefs.current['BB_upper']) chart.removeSeries(indicatorSeriesRefs.current['BB_upper']);
      if (indicatorSeriesRefs.current['BB_lower']) chart.removeSeries(indicatorSeriesRefs.current['BB_lower']);
      if (indicatorSeriesRefs.current['BB_basis']) chart.removeSeries(indicatorSeriesRefs.current['BB_basis']);
      delete indicatorSeriesRefs.current['BB'];
      delete indicatorSeriesRefs.current['BB_upper'];
      delete indicatorSeriesRefs.current['BB_lower'];
      delete indicatorSeriesRefs.current['BB_basis'];
    }

    // Add and update active indicators
    activeIndicators.forEach((ind) => {
      if (ind === 'SMA') {
        if (!indicatorSeriesRefs.current['SMA']) {
          indicatorSeriesRefs.current['SMA'] = chart.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 2, title: 'SMA 14', crosshairMarkerVisible: false });
        }
        indicatorSeriesRefs.current['SMA'].setData(calculateSMA(chartData, 14));
      } else if (ind === 'EMA') {
        if (!indicatorSeriesRefs.current['EMA']) {
          indicatorSeriesRefs.current['EMA'] = chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 2, title: 'EMA 14', crosshairMarkerVisible: false });
        }
        indicatorSeriesRefs.current['EMA'].setData(calculateEMA(chartData, 14));
      } else if (ind === 'VWAP') {
        if (!indicatorSeriesRefs.current['VWAP']) {
          indicatorSeriesRefs.current['VWAP'] = chart.addSeries(LineSeries, { color: '#8b5cf6', lineWidth: 2, title: 'VWAP', crosshairMarkerVisible: false });
        }
        indicatorSeriesRefs.current['VWAP'].setData(calculateVWAP(chartData));
      } else if (ind === 'BB') {
        if (!indicatorSeriesRefs.current['BB']) {
          const upper = chart.addSeries(LineSeries, { color: '#38bdf8', lineWidth: 1, title: 'BB Upper', crosshairMarkerVisible: false, lineStyle: 2 });
          const lower = chart.addSeries(LineSeries, { color: '#38bdf8', lineWidth: 1, title: 'BB Lower', crosshairMarkerVisible: false, lineStyle: 2 });
          const basis = chart.addSeries(LineSeries, { color: '#14b8a6', lineWidth: 1, title: 'BB Basis', crosshairMarkerVisible: false });
          indicatorSeriesRefs.current['BB'] = { upper, lower, basis };
        }
        const bb = calculateBollingerBands(chartData, 20, 2);
        indicatorSeriesRefs.current['BB'].upper.setData(bb.upper);
        indicatorSeriesRefs.current['BB'].lower.setData(bb.lower);
        indicatorSeriesRefs.current['BB'].basis.setData(bb.basis);
      }
    });
  }, [indicators, chartData]);

  // 4. Fetch historical data and setup live Socket.IO subscriptions
  useEffect(() => {
    let activeUnsubscribe: (() => void) | null = null;
    setIsLoading(true);

    const loadData = async () => {
      try {
        const isIntraday = ['1m', '5m', '15m', '1h'].includes(timeframe);
        const isFutures = symbol.toUpperCase().includes('FUT');
        
        let histData: any[] = [];
        const isDemo = typeof window !== 'undefined' && 
          (window.location.hostname.includes('vercel.app') || window.location.pathname.startsWith('/demo') || window.location.pathname.includes('/api/demo'));

        if (isDemo) {
          histData = generateMockHistoricalData(symbol, timeframe, effectiveBucketSize);
        } else {
          try {
            if (isIntraday || isFutures) {
              const url = `http://127.0.0.1:5000/api/historical?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&bucket_size=${bucketSize}&multiplier=${multiplier}`;
              const res = await fetch(url);
              if (res.ok) {
                histData = await res.json();
              } else {
                throw new Error();
              }
            } else {
              const url = `${API_BASE_URL}/data/candlesticks/${encodeURIComponent(symbol)}`;
              const res = await fetch(url);
              if (res.ok) {
                const histResponse = await res.json();
                histData = histResponse.data;
              } else {
                throw new Error();
              }
            }
          } catch {
            console.log(`[CandleChart] Local server offline, falling back to mock historical data for ${symbol}`);
            histData = generateMockHistoricalData(symbol, timeframe, effectiveBucketSize);
          }
        }

        // Populate Lightweight Charts series
        if (Array.isArray(histData)) {
          setChartData(histData);
          if (candleSeriesRef.current) candleSeriesRef.current.setData(histData);
          if (footprintSeriesRef.current) footprintSeriesRef.current.setData(histData);
          
          if (histData.length > 0) {
            setLegendData(histData[histData.length - 1]);
            // Fit content
            chartRef.current?.timeScale().fitContent();
          }
        }

        // Subscribe to live tick updates
        const lastCandle = histData && histData.length > 0 ? histData[histData.length - 1] : null;
        activeUnsubscribe = socketManager.subscribe(
          symbol,
          chartId,
          timeframe,
          bucketSize,
          multiplier,
          lastCandle,
          (liveUpdate: any) => {
            // Convert numeric timestamp to YYYY-MM-DD string for 1d timeframe to match historical dates
            let formattedUpdate = { ...liveUpdate };
            if (timeframe === '1d' && typeof liveUpdate.time === 'number') {
              const date = new Date(liveUpdate.time * 1000);
              const yyyy = date.getFullYear();
              const mm = String(date.getMonth() + 1).padStart(2, '0');
              const dd = String(date.getDate()).padStart(2, '0');
              formattedUpdate.time = `${yyyy}-${mm}-${dd}`;
            }

            // Update local state with live ticks
            setChartData((prev) => {
              const copy = [...prev];
              if (copy.length === 0) {
                copy.push(formattedUpdate);
              } else {
                const idx = copy.findIndex((d) => d.time === formattedUpdate.time);
                if (idx !== -1) {
                  copy[idx] = formattedUpdate;
                } else {
                  copy.push(formattedUpdate);
                }
              }
              return copy;
            });

            // Update series
            if (candleSeriesRef.current) candleSeriesRef.current.update(formattedUpdate);
            if (footprintSeriesRef.current) footprintSeriesRef.current.update(formattedUpdate);

            setLegendData(formattedUpdate);

            // Forward full DOM updates if available and listener exists
            if (onBookUpdate && liveUpdate.bids) {
              onBookUpdate(liveUpdate);
            }
          }
        );
      } catch (err) {
        console.error('Failed loading historical/live data:', err);
      } finally {
        setIsLoading(false);
      }
    };

    loadData();

    return () => {
      if (activeUnsubscribe) activeUnsubscribe();
    };
  }, [symbol, timeframe, bucketSize, multiplier]);

  // Display fields
  const activeCandle = legendData || (chartData.length > 0 ? chartData[chartData.length - 1] : null);

  return (
    <div
      onClick={onSelect}
      className={`relative flex flex-col h-full bg-[#0d1117] rounded-xl overflow-hidden cursor-pointer select-none transition-all ${
        isActive ? 'border-2 border-[#64748b]' : 'border border-[#1e2d40] hover:border-[#1e3a5f]'
      }`}
    >
      {/* Legend & Controls Overlay */}
      <div className="absolute top-3 left-4 z-20 pointer-events-none flex flex-col text-xs text-[#b2b5be]">
        <div className="flex items-center gap-2">
          <span className="font-bold text-white num">{symbol}</span>
          <span className="bg-[#1e2d40] px-1 rounded font-semibold">{timeframe}</span>
          <span className="text-[#64748b] num">({bucketSize}×{multiplier})</span>
        </div>
        {activeCandle && (
          <div className="flex flex-wrap gap-x-2.5 gap-y-0.5 mt-1.5 font-medium text-[11px] bg-[#070a0f]/80 px-2 py-1 rounded border border-[#1e2d40]/40 backdrop-blur-sm">
            <span>O: <span className="text-white num">{activeCandle.open?.toFixed(2)}</span></span>
            <span>H: <span className="text-[#00d97e] num">{activeCandle.high?.toFixed(2)}</span></span>
            <span>L: <span className="text-[#ff4d6a] num">{activeCandle.low?.toFixed(2)}</span></span>
            <span>C: <span className="text-white num">{activeCandle.close?.toFixed(2)}</span></span>
            <span>V: <span className="text-white num">{activeCandle.volume?.toLocaleString('en-IN')}</span></span>
            {activeCandle.delta !== undefined && (
              <span>
                Δ:{' '}
                <span className={`num ${activeCandle.delta >= 0 ? 'text-[#00d97e]' : 'text-[#ff4d6a]'}`}>
                  {activeCandle.delta >= 0 ? '+' : ''}{activeCandle.delta.toLocaleString('en-IN')}
                </span>
              </span>
            )}
            {activeCandle.cum_delta !== undefined && (
              <span>
                ΣΔ:{' '}
                <span className={`num ${activeCandle.cum_delta >= 0 ? 'text-[#00d97e]' : 'text-[#ff4d6a]'}`}>
                  {activeCandle.cum_delta >= 0 ? '+' : ''}{activeCandle.cum_delta.toLocaleString('en-IN')}
                </span>
              </span>
            )}
          </div>
        )}
      </div>

      {isLoading && (
        <div className="absolute inset-0 z-30 bg-[#0d1117]/60 flex items-center justify-center backdrop-blur-xs">
          <div className="w-8 h-8 border-4 border-t-transparent border-[#00d97e] rounded-full animate-spin" />
        </div>
      )}

      {/* Main Chart Container */}
      <div ref={chartContainerRef} className="flex-1 w-full h-full" />

      {/* Volume Profile Canvas Overlay */}
      {showVolumeProfile && chartRef.current && (candleSeriesRef.current || footprintSeriesRef.current) && (
        <VolumeProfile
          chart={chartRef.current}
          series={(chartType === 'footprint' ? footprintSeriesRef.current : candleSeriesRef.current)}
          data={chartData}
          visibleRange={visibleRange}
          bucketSize={effectiveBucketSize}
        />
      )}
    </div>
  );
}
