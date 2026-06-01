import React, { useEffect, useRef } from 'react';
import { IChartApi, ISeriesApi } from 'lightweight-charts';

interface VolumeProfileProps {
  chart: IChartApi | null;
  series: ISeriesApi<any> | null;
  data: any[];
  visibleRange: { from: number; to: number } | null;
  bucketSize: number;
}

export default function VolumeProfile({
  chart,
  series,
  data,
  visibleRange,
  bucketSize,
}: VolumeProfileProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !chart || !series || data.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const container = canvas.parentElement;
    if (!container) return;

    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;

    let visibleData = data;
    if (visibleRange) {
      visibleData = data.filter(
        (d) => d.time >= visibleRange.from && d.time <= visibleRange.to
      );
    }

    if (visibleData.length === 0) return;

    const profile: Map<number, { buy: number; sell: number; total: number }> = new Map();

    visibleData.forEach((candle) => {
      if (candle.footprint && Array.isArray(candle.footprint)) {
        candle.footprint.forEach((fp: any) => {
          const price = fp.priceLevel ?? fp.price;
          const buy = fp.buyVolume ?? fp.buy ?? 0;
          const sell = fp.sellVolume ?? fp.sell ?? 0;
          if (price !== undefined) {
            const roundedPrice = Math.round(price * 100) / 100;
            const existing = profile.get(roundedPrice) || { buy: 0, sell: 0, total: 0 };
            existing.buy += buy;
            existing.sell += sell;
            existing.total += buy + sell;
            profile.set(roundedPrice, existing);
          }
        });
      } else {
        const roundedPrice = Math.round(candle.close / bucketSize) * bucketSize;
        const roundedPriceKey = Math.round(roundedPrice * 100) / 100;
        const existing = profile.get(roundedPriceKey) || { buy: 0, sell: 0, total: 0 };
        const buy = candle.buy_vol ?? candle.volume / 2;
        const sell = candle.sell_vol ?? candle.volume / 2;
        existing.buy += buy;
        existing.sell += sell;
        existing.total += candle.volume;
        profile.set(roundedPriceKey, existing);
      }
    });

    if (profile.size === 0) return;

    const sortedLevels = Array.from(profile.entries()).sort((a, b) => b[0] - a[0]);

    let maxVolume = 0;
    let pocPrice = 0;
    let totalVolume = 0;

    sortedLevels.forEach(([price, val]) => {
      totalVolume += val.total;
      if (val.total > maxVolume) {
        maxVolume = val.total;
        pocPrice = price;
      }
    });

    const sortedByVolume = [...sortedLevels].sort((a, b) => b[1].total - a[1].total);
    const valueAreaVolumeTgt = totalVolume * 0.7;
    let accumulatedVolume = 0;
    const valueAreaPrices: Set<number> = new Set();

    for (const [price, val] of sortedByVolume) {
      accumulatedVolume += val.total;
      valueAreaPrices.add(price);
      if (accumulatedVolume >= valueAreaVolumeTgt) break;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const chartWidth = canvas.width;
    const profileMaxWidth = chartWidth * 0.15; // Muted profile width to prevent chart clutter

    ctx.save();

    sortedLevels.forEach(([price, val]) => {
      const y = series.priceToCoordinate(price);
      if (y === null || isNaN(y) || y < 0 || y > canvas.height) return;

      const yNext = series.priceToCoordinate(price + bucketSize);
      let barHeight = 4;
      if (yNext !== null && !isNaN(yNext)) {
        barHeight = Math.max(1, Math.abs(y - yNext) - 0.5);
      }

      const barWidth = (val.total / maxVolume) * profileMaxWidth;
      const isValueArea = valueAreaPrices.has(price);
      const isPoc = Math.abs(price - pocPrice) < 0.001;

      const buyWidth = (val.buy / val.total) * barWidth;
      const sellWidth = barWidth - buyWidth;

      // Render Buy/Sell horizontal segments
      ctx.fillStyle = isValueArea ? 'rgba(0, 217, 126, 0.25)' : 'rgba(0, 217, 126, 0.08)';
      ctx.fillRect(0, y - barHeight / 2, buyWidth, barHeight);

      ctx.fillStyle = isValueArea ? 'rgba(255, 77, 106, 0.25)' : 'rgba(255, 77, 106, 0.08)';
      ctx.fillRect(buyWidth, y - barHeight / 2, sellWidth, barHeight);

      if (isPoc) {
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(profileMaxWidth + 30, y);
        ctx.stroke();

        ctx.fillStyle = '#f59e0b';
        ctx.font = 'bold 9px var(--font-mono), monospace';
        ctx.fillText('POC', profileMaxWidth + 8, y - 3);
      }
    });

    ctx.restore();
  }, [chart, series, data, visibleRange, bucketSize]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none z-10"
      style={{ width: '100%', height: '100%' }}
    />
  );
}
