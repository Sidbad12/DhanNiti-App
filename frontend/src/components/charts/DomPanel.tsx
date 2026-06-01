import React from 'react';

interface BookLevel {
  price: number;
  qty: number;
  orders: number;
  level: number;
}

interface DomPanelProps {
  symbol: string;
  ltp?: number;
  bids?: BookLevel[];
  asks?: BookLevel[];
  tbq?: number;
  tsq?: number;
  sentiment?: number;
  imbalance_50?: number;
}

export default function DomPanel({
  symbol,
  ltp = 0,
  bids = [],
  asks = [],
  tbq = 0,
  tsq = 0,
  sentiment = 0,
  imbalance_50 = 0,
}: DomPanelProps) {
  // Find maximum quantity to scale the depth bars
  const maxQty = Math.max(
    ...bids.map((b) => b.qty),
    ...asks.map((a) => a.qty),
    1
  );

  // Calculate sentiment percentages
  const totalQty = tbq + tsq;
  const buyPct = totalQty > 0 ? (tbq / totalQty) * 100 : 50;
  const sellPct = totalQty > 0 ? (tsq / totalQty) * 100 : 50;

  // Format numbers
  const formatQty = (num: number) => {
    return num.toLocaleString('en-IN');
  };

  const formatPrice = (num: number) => {
    return num.toFixed(2);
  };

  return (
    <div className="flex flex-col h-full bg-[#0d1117] border border-[#1e2d40] rounded-xl overflow-hidden text-white">
      {/* Header */}
      <div className="p-4 border-b border-[#1e2d40] bg-[#070a0f] flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex flex-col">
            <span className="text-xs text-[#64748b] font-semibold uppercase tracking-wider">DOM Panel</span>
            <span className="text-sm font-bold text-white num">{symbol}</span>
          </div>
          <div className="flex flex-col items-end">
            <span className="text-xs text-[#64748b] font-semibold">LTP</span>
            <span className="text-sm font-bold text-[#00d97e] num">{formatPrice(ltp)}</span>
          </div>
        </div>

        {/* Sentiment bar */}
        <div className="mt-2">
          <div className="flex justify-between text-[10px] text-[#64748b] font-bold mb-1">
            <span className="text-[#00d97e]">BUY: {buyPct.toFixed(1)}%</span>
            <span className="text-[#ff4d6a]">SELL: {sellPct.toFixed(1)}%</span>
          </div>
          <div className="h-1.5 w-full bg-[#ff4d6a]/20 rounded-full overflow-hidden flex">
            <div className="h-full bg-[#00d97e]" style={{ width: `${buyPct}%` }} />
          </div>
        </div>

        {/* Sentiment/Imbalance summary */}
        <div className="grid grid-cols-2 gap-2 mt-1">
          <div className="bg-[#111827] p-2 rounded border border-[#1e2d40]/40 flex flex-col">
            <span className="text-[9px] text-[#64748b] font-semibold">Total Bid Qty</span>
            <span className="text-xs font-bold text-[#00d97e] num">{formatQty(tbq)}</span>
          </div>
          <div className="bg-[#111827] p-2 rounded border border-[#1e2d40]/40 flex flex-col items-end">
            <span className="text-[9px] text-[#64748b] font-semibold">Total Ask Qty</span>
            <span className="text-xs font-bold text-[#ff4d6a] num">{formatQty(tsq)}</span>
          </div>
        </div>
      </div>

      {/* Book table */}
      <div className="flex-1 overflow-y-auto p-2">
        <div className="grid grid-cols-2 gap-4 h-full">
          {/* Bids Column */}
          <div className="flex flex-col">
            <div className="grid grid-cols-3 text-[10px] text-[#64748b] font-bold pb-2 border-b border-[#1e2d40]/50 sticky top-0 bg-[#0d1117] z-10">
              <span>Orders</span>
              <span className="text-right">Qty</span>
              <span className="text-right">Bid Price</span>
            </div>
            <div className="flex-1 flex flex-col mt-1">
              {bids.slice(0, 20).map((bid) => (
                <div
                  key={bid.level}
                  className="grid grid-cols-3 py-1.5 text-xs border-b border-[#1e2d40]/20 relative hover:bg-[#161f2e] transition-colors"
                >
                  {/* Depth Bar Background */}
                  <div
                    className="absolute right-0 top-0 bottom-0 bg-[#00d97e]/10 pointer-events-none transition-all duration-300"
                    style={{ width: `${(bid.qty / maxQty) * 100}%` }}
                  />
                  <span className="text-[#64748b] num z-10">{bid.orders}</span>
                  <span className="text-right text-[#e2e8f0] font-semibold num z-10">
                    {formatQty(bid.qty)}
                  </span>
                  <span className="text-right text-[#00d97e] font-bold num z-10">
                    {formatPrice(bid.price)}
                  </span>
                </div>
              ))}
              {bids.length === 0 && (
                <div className="flex items-center justify-center flex-1 text-xs text-[#64748b] py-8">
                  No bids data
                </div>
              )}
            </div>
          </div>

          {/* Asks Column */}
          <div className="flex flex-col">
            <div className="grid grid-cols-3 text-[10px] text-[#64748b] font-bold pb-2 border-b border-[#1e2d40]/50 sticky top-0 bg-[#0d1117] z-10">
              <span>Ask Price</span>
              <span className="text-right">Qty</span>
              <span className="text-right">Orders</span>
            </div>
            <div className="flex-1 flex flex-col mt-1">
              {asks.slice(0, 20).map((ask) => (
                <div
                  key={ask.level}
                  className="grid grid-cols-3 py-1.5 text-xs border-b border-[#1e2d40]/20 relative hover:bg-[#161f2e] transition-colors"
                >
                  {/* Depth Bar Background */}
                  <div
                    className="absolute left-0 top-0 bottom-0 bg-[#ff4d6a]/10 pointer-events-none transition-all duration-300"
                    style={{ width: `${(ask.qty / maxQty) * 100}%` }}
                  />
                  <span className="text-[#ff4d6a] font-bold num z-10">
                    {formatPrice(ask.price)}
                  </span>
                  <span className="text-right text-[#e2e8f0] font-semibold num z-10">
                    {formatQty(ask.qty)}
                  </span>
                  <span className="text-right text-[#64748b] num z-10">{ask.orders}</span>
                </div>
              ))}
              {asks.length === 0 && (
                <div className="flex items-center justify-center flex-1 text-xs text-[#64748b] py-8">
                  No asks data
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Footer Info */}
      <div className="p-3 bg-[#070a0f] border-t border-[#1e2d40] text-[10px] text-[#64748b] flex justify-between">
        <span>Order Imbalance (50L):</span>
        <span className={`font-bold num ${imbalance_50 >= 0 ? 'text-[#00d97e]' : 'text-[#ff4d6a]'}`}>
          {(imbalance_50 * 100).toFixed(2)}%
        </span>
      </div>
    </div>
  );
}
