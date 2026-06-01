"use client";
import React, { useEffect, useRef } from "react";
import { createChart, ColorType, CandlestickSeries, HistogramSeries, createSeriesMarkers } from "lightweight-charts";

interface OHLCV {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface Signal {
  time: string;
  action: "BUY" | "SELL";
}

interface CandlestickChartProps {
  data: OHLCV[];
  signals?: Signal[];
  colors?: {
    backgroundColor?: string;
    textColor?: string;
    upColor?: string;
    downColor?: string;
  };
}

export function CandlestickChart({
  data,
  signals = [],
  colors: {
    backgroundColor = "transparent",
    textColor = "#94a3b8",
    upColor = "#00d97e",
    downColor = "#ff4d6a",
  } = {},
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: backgroundColor },
        textColor,
        fontFamily: "JetBrains Mono, monospace",
      },
      grid: {
        vertLines: { color: "#1e2d4088" },
        horzLines: { color: "#1e2d4088" },
      },
      width: containerRef.current.clientWidth,
      height: 300,
      timeScale: { borderColor: "#1e2d40" },
      rightPriceScale: { borderColor: "#1e2d40" },
      crosshair: {
        vertLine: { color: "#00d97e55", labelBackgroundColor: "#0d1117" },
        horzLine: { color: "#00d97e55", labelBackgroundColor: "#0d1117" },
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor,
      downColor,
      borderVisible: false,
      wickUpColor: upColor,
      wickDownColor: downColor,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: {
        type: "volume",
      },
      priceScaleId: "", // Overlay on the same pane
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    // Ensure data is sorted by time and deduplicated
    const sorted = [...data]
      .sort((a, b) => a.time.localeCompare(b.time))
      .filter((d, i, arr) => i === 0 || d.time !== arr[i - 1].time);

    series.setData(sorted as Parameters<typeof series.setData>[0]);

    const volumeData = sorted
      .filter((d) => typeof d.volume === "number")
      .map((d) => ({
        time: d.time,
        value: d.volume!,
        color: d.close >= d.open ? `${upColor}33` : `${downColor}33`,
      }));

    volumeSeries.setData(volumeData as Parameters<typeof volumeSeries.setData>[0]);

    if (signals.length > 0) {
      const markers = signals.map(s => ({
        time: s.time as Parameters<typeof series.setData>[0][number]["time"],
        position: s.action === "BUY" ? "belowBar" : "aboveBar",
        color: s.action === "BUY" ? upColor : downColor,
        shape: s.action === "BUY" ? "arrowUp" : "arrowDown",
        text: s.action,
        size: 2,
      }));
      const markersApi = createSeriesMarkers(series);
      markersApi.setMarkers(markers as Parameters<typeof markersApi.setMarkers>[0]);
    }

    chart.timeScale().fitContent();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data, signals, backgroundColor, textColor, upColor, downColor]);

  if (data.length === 0) {
    return (
      <div className="w-full h-[300px] flex items-center justify-center font-mono text-xs rounded-lg"
        style={{ color: "#374151", border: "1px solid #1e2d40" }}>
        Loading chart data...
      </div>
    );
  }

  return <div ref={containerRef} style={{ width: "100%", height: "300px" }} />;
}
