import React, { useState, useEffect } from 'react';
import CandleChart from './CandleChart';
import DomPanel from './DomPanel';
import SymbolSearch from './SymbolSearch';

interface ChartConfig {
  id: string;
  symbol: string;
  timeframe: string;
  bucketSize: number;
  multiplier: number;
  chartType: 'candlestick' | 'footprint';
  showVolumeProfile: boolean;
}

const DEFAULT_CHARTS: ChartConfig[] = [
  {
    id: 'chart-0',
    symbol: 'NSE:NIFTY26JANFUT',
    timeframe: '5m',
    bucketSize: 0.05,
    multiplier: 100,
    chartType: 'footprint',
    showVolumeProfile: true,
  },
  {
    id: 'chart-1',
    symbol: 'NSE:NIFTY26JANFUT',
    timeframe: '15m',
    bucketSize: 0.05,
    multiplier: 100,
    chartType: 'footprint',
    showVolumeProfile: true,
  },
  {
    id: 'chart-2',
    symbol: 'NSE:SBIN-EQ',
    timeframe: '5m',
    bucketSize: 0.05,
    multiplier: 100,
    chartType: 'candlestick',
    showVolumeProfile: true,
  },
  {
    id: 'chart-3',
    symbol: 'NSE:TCS-EQ',
    timeframe: '5m',
    bucketSize: 0.05,
    multiplier: 100,
    chartType: 'candlestick',
    showVolumeProfile: true,
  },
];

export default function ChartLayout({ initialSymbol }: { initialSymbol?: string }) {
  const [layoutCount, setLayoutCount] = useState<1 | 2 | 4>(1);
  const [activeChartIdx, setActiveChartIdx] = useState<number>(0);
  const [charts, setCharts] = useState<ChartConfig[]>(() => {
    const base = [...DEFAULT_CHARTS];
    if (initialSymbol) {
      base[0] = { ...base[0], symbol: initialSymbol };
    }
    return base;
  });
  const [selectedBookData, setSelectedBookData] = useState<any>(null);

  // Sync initialSymbol to active chart when it changes
  useEffect(() => {
    if (initialSymbol) {
      setCharts((prev) => {
        const copy = [...prev];
        copy[0] = { ...copy[0], symbol: initialSymbol };
        return copy;
      });
    }
  }, [initialSymbol]);

  // Update config of the currently active chart
  const updateActiveChartConfig = (updater: (prev: ChartConfig) => ChartConfig) => {
    setCharts((prev) => {
      const copy = [...prev];
      copy[activeChartIdx] = updater(copy[activeChartIdx]);
      return copy;
    });
  };

  const activeChart = charts[activeChartIdx];

  // Grid style generator
  const getGridClass = () => {
    switch (layoutCount) {
      case 1:
        return 'grid-cols-1 grid-rows-1';
      case 2:
        return 'grid-cols-2 grid-rows-1';
      case 4:
        return 'grid-cols-2 grid-rows-2';
      default:
        return 'grid-cols-2 grid-rows-1';
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#070a0f] text-white overflow-hidden">
      {/* Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-[#0d1117] border-b border-[#1e2d40] z-20">
        <div className="flex items-center gap-4 flex-1">
          {/* Back Button */}
          <button 
            onClick={() => window.location.href = '/app/dashboard'}
            className="text-slate-400 hover:text-white font-mono text-xs transition-colors"
          >
            ← BACK TO QUANT
          </button>
          
          <span className="text-slate-600">|</span>

          {/* Symbol Search */}
          <SymbolSearch
            onSelectSymbol={(sym) =>
              updateActiveChartConfig((prev) => ({ ...prev, symbol: sym }))
            }
            currentSymbol={activeChart.symbol}
          />

          {/* Timeframe selector */}
          <div className="flex bg-[#070a0f] p-1 rounded-lg border border-[#1e2d40]">
            {['1m', '5m', '15m', '1d'].map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() =>
                  updateActiveChartConfig((prev) => ({ ...prev, timeframe: tf }))
                }
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                  activeChart.timeframe === tf
                    ? 'bg-[#1e2d40] text-white'
                    : 'text-[#64748b] hover:text-white'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Chart Type Toggle */}
          <div className="flex bg-[#070a0f] p-1 rounded-lg border border-[#1e2d40]">
            {(['candlestick', 'footprint'] as const).map((type) => (
              <button
                key={type}
                type="button"
                onClick={() =>
                  updateActiveChartConfig((prev) => ({ ...prev, chartType: type }))
                }
                className={`px-3 py-1.5 text-xs font-semibold rounded-md capitalize transition-all ${
                  activeChart.chartType === type
                    ? 'bg-[#1e2d40] text-white'
                    : 'text-[#64748b] hover:text-white'
                }`}
              >
                {type}
              </button>
            ))}
          </div>

          {/* Volume Profile Toggle */}
          <button
            type="button"
            onClick={() =>
              updateActiveChartConfig((prev) => ({
                ...prev,
                showVolumeProfile: !prev.showVolumeProfile,
              }))
            }
            className={`px-3 py-2 text-xs font-semibold rounded-lg border transition-all ${
              activeChart.showVolumeProfile
                ? 'bg-[#00d97e]/15 border-[#00d97e] text-[#00d97e]'
                : 'bg-transparent border-[#1e2d40] text-[#64748b] hover:text-white'
            }`}
          >
            Volume Profile
          </button>
        </div>

        {/* Layout Selectors */}
        <div className="flex bg-[#070a0f] p-1 rounded-lg border border-[#1e2d40] gap-1">
          {([1, 2, 4] as const).map((count) => (
            <button
              key={count}
              type="button"
              onClick={() => {
                setLayoutCount(count);
                if (activeChartIdx >= count) {
                  setActiveChartIdx(0);
                }
              }}
              className={`p-1.5 rounded-md transition-all ${
                layoutCount === count
                  ? 'bg-[#1e2d40] text-white font-bold'
                  : 'text-[#64748b] hover:text-white'
              }`}
              title={`${count} Panel Layout`}
            >
              <div className="w-5 h-5 flex items-center justify-center text-xs">
                {count === 1 ? '⬛' : count === 2 ? '▌▐' : '⊞'}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Main Work Area: Grid Charts + DOM Panel */}
      <div className="flex-1 flex overflow-hidden p-4 gap-4">
        {/* Charts Grid */}
        <div className={`flex-1 grid gap-4 ${getGridClass()}`}>
          {charts.slice(0, layoutCount).map((config, idx) => (
            <CandleChart
              key={config.id}
              chartId={config.id}
              symbol={config.symbol}
              timeframe={config.timeframe}
              bucketSize={config.bucketSize}
              multiplier={config.multiplier}
              chartType={config.chartType}
              showVolumeProfile={config.showVolumeProfile}
              isActive={idx === activeChartIdx}
              onSelect={() => {
                setActiveChartIdx(idx);
                setSelectedBookData(null); // Clear DOM data to prevent stale display
              }}
              onBookUpdate={(book) => {
                if (idx === activeChartIdx) {
                  setSelectedBookData(book);
                }
              }}
            />
          ))}
        </div>

        {/* Depth of Market (DOM) Side Panel */}
        <div className="w-80 shrink-0 h-full">
          <DomPanel
            symbol={activeChart.symbol}
            ltp={selectedBookData?.ltp ?? activeChart.symbol ? 0 : undefined}
            bids={selectedBookData?.bids ?? []}
            asks={selectedBookData?.asks ?? []}
            tbq={selectedBookData?.tbq ?? 0}
            tsq={selectedBookData?.tsq ?? 0}
            sentiment={selectedBookData?.sentiment ?? 0}
            imbalance_50={selectedBookData?.imbalance_50 ?? 0}
          />
        </div>
      </div>
    </div>
  );
}
