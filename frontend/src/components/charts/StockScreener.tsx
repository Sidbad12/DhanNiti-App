import React, { useState } from 'react';

export default function StockScreener({ onSelectSymbol }: { onSelectSymbol?: (sym: string) => void }) {
  const [filter, setFilter] = useState('Top Gainers');
  const [timeframe, setTimeframe] = useState('1D');

  const filters = ['Top Gainers', 'Top Losers', 'High Volume', 'Overbought', 'Oversold'];
  
  // Mock data for the screener
  const results = [
    { symbol: 'RELIANCE', name: 'Reliance Industries', price: 2850.45, change: 1.2, volume: '4.5M', rsi: 65, vwap: 2840 },
    { symbol: 'TCS', name: 'Tata Consultancy', price: 3920.10, change: 0.8, volume: '2.1M', rsi: 58, vwap: 3910 },
    { symbol: 'HDFCBANK', name: 'HDFC Bank', price: 1540.25, change: -0.5, volume: '8.2M', rsi: 42, vwap: 1550 },
    { symbol: 'INFY', name: 'Infosys', price: 1420.80, change: 2.4, volume: '5.6M', rsi: 72, vwap: 1400 },
    { symbol: 'ICICIBANK', name: 'ICICI Bank', price: 1080.50, change: 0.3, volume: '6.4M', rsi: 55, vwap: 1075 }
  ].sort((a, b) => {
    if (filter === 'Top Gainers') return b.change - a.change;
    if (filter === 'Top Losers') return a.change - b.change;
    if (filter === 'High Volume') return parseFloat(b.volume) - parseFloat(a.volume);
    if (filter === 'Overbought') return b.rsi - a.rsi;
    if (filter === 'Oversold') return a.rsi - b.rsi;
    return 0;
  });

  return (
    <div className="flex flex-col h-full bg-[#0d1117]">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-[#1e2d40] bg-[#070a0f]">
        <div className="flex items-center gap-3">
          <span className="text-base">🔎</span>
          <div>
            <div className="font-mono text-[11px] font-bold uppercase tracking-widest text-[#64748b]">Advanced Screener</div>
            <div className="font-mono text-[10px] text-[#374151]">Filter by technicals & volume</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select 
            className="bg-[#111827] border border-[#1e2d40] text-xs font-mono text-[#e2e8f0] rounded px-2 py-1 outline-none focus:border-[#3b82f6]"
            value={filter}
            onChange={e => setFilter(e.target.value)}
          >
            {filters.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
          <select 
            className="bg-[#111827] border border-[#1e2d40] text-xs font-mono text-[#e2e8f0] rounded px-2 py-1 outline-none focus:border-[#3b82f6]"
            value={timeframe}
            onChange={e => setTimeframe(e.target.value)}
          >
            {['15M', '1H', '1D', '1W'].map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto flex-1">
        <table className="w-full text-left text-xs font-mono whitespace-nowrap">
          <thead className="bg-[#111827]/50 text-[#64748b] sticky top-0">
            <tr>
              <th className="px-4 py-2 font-medium">Symbol</th>
              <th className="px-4 py-2 font-medium">Price</th>
              <th className="px-4 py-2 font-medium">Chg %</th>
              <th className="px-4 py-2 font-medium">Vol</th>
              <th className="px-4 py-2 font-medium">RSI</th>
              <th className="px-4 py-2 font-medium">VWAP</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e2d40]">
            {results.map(row => (
              <tr 
                key={row.symbol} 
                className="hover:bg-[#111827] cursor-pointer transition-colors"
                onClick={() => onSelectSymbol && onSelectSymbol(`${row.symbol}.NS`)}
              >
                <td className="px-4 py-3">
                  <div className="font-bold text-white">{row.symbol}</div>
                  <div className="text-[9px] text-[#64748b]">{row.name}</div>
                </td>
                <td className="px-4 py-3 text-white">₹{row.price.toFixed(2)}</td>
                <td className={`px-4 py-3 font-bold ${row.change >= 0 ? 'text-[#00d97e]' : 'text-[#ff4d6a]'}`}>
                  {row.change >= 0 ? '+' : ''}{row.change}%
                </td>
                <td className="px-4 py-3 text-[#e2e8f0]">{row.volume}</td>
                <td className={`px-4 py-3 ${row.rsi >= 70 ? 'text-[#ff4d6a]' : row.rsi <= 30 ? 'text-[#00d97e]' : 'text-[#e2e8f0]'}`}>{row.rsi}</td>
                <td className="px-4 py-3 text-[#e2e8f0]">{row.vwap}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
