import React, { useState, useEffect, useRef } from 'react';

interface SymbolItem {
  symbol: string;
  description: string;
  exchange: string;
  type: string;
  expiry?: string;
  lot_size?: number;
}

interface SymbolSearchProps {
  onSelectSymbol: (symbol: string) => void;
  currentSymbol?: string;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_CHARTING_API_URL || 'http://127.0.0.1:5000';

export default function SymbolSearch({ onSelectSymbol, currentSymbol }: SymbolSearchProps) {
  const [query, setQuery] = useState(currentSymbol || '');
  const [results, setResults] = useState<SymbolItem[]>([]);
  const [category, setCategory] = useState<'All' | 'Equity' | 'Futures'>('All');
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Search logic
  useEffect(() => {
    if (!isOpen || query.trim().length < 2) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/symbols?q=${encodeURIComponent(query)}&category=${category}&limit=20`
        );
        if (response.ok) {
          const data = await response.json();
          setResults(data);
          setSelectedIndex(0);
        }
      } catch (err) {
        console.error('Failed to search symbols:', err);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query, category, isOpen]);

  // Click outside to close
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        setIsOpen(true);
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % Math.max(results.length, 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + results.length) % Math.max(results.length, 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (selectedIndex >= 0 && selectedIndex < results.length) {
        handleSelect(results[selectedIndex]);
      } else if (results.length > 0) {
        handleSelect(results[0]);
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false);
      inputRef.current?.blur();
    }
  };

  const handleSelect = (item: SymbolItem) => {
    setQuery(item.symbol);
    onSelectSymbol(item.symbol);
    setIsOpen(false);
  };

  return (
    <div className="relative w-full max-w-md" ref={dropdownRef}>
      <div className="relative flex items-center">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search symbol (e.g. NIFTY, SBIN...)"
          className="w-full h-10 px-4 pr-10 text-sm bg-[#0d1117] text-white placeholder-[#64748b] border border-[#1e2d40] rounded-lg focus:outline-none focus:border-[#3b82f6] focus:ring-1 focus:ring-[#3b82f6] transition-all num"
        />
        {isLoading ? (
          <div className="absolute right-3 w-4 h-4 border-2 border-t-transparent border-[#3b82f6] rounded-full animate-spin" />
        ) : (
          <svg
            className="absolute right-3 w-4 h-4 text-[#64748b]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        )}
      </div>

      {isOpen && (query.trim().length >= 2 || results.length > 0) && (
        <div className="absolute z-50 w-full mt-1 bg-[#0d1117] border border-[#1e2d40] rounded-lg shadow-xl overflow-hidden animate-fade-in-up">
          {/* Categories Tab */}
          <div className="flex border-b border-[#1e2d40] bg-[#070a0f] p-1 gap-1">
            {(['All', 'Equity', 'Futures'] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                className={`flex-1 py-1 text-xs font-semibold rounded-md transition-all ${
                  category === cat
                    ? 'bg-[#1e2d40] text-white'
                    : 'text-[#64748b] hover:text-white hover:bg-[#111827]'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* Results List */}
          <div className="max-h-64 overflow-y-auto">
            {results.length === 0 ? (
              <div className="px-4 py-3 text-xs text-[#64748b] text-center">
                {isLoading ? 'Searching...' : 'No symbols found'}
              </div>
            ) : (
              results.map((item, idx) => (
                <div
                  key={item.symbol}
                  onClick={() => handleSelect(item)}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`flex items-center justify-between px-4 py-2.5 cursor-pointer border-b border-[#1e2d40]/30 transition-all ${
                    idx === selectedIndex ? 'bg-[#161f2e]' : 'hover:bg-[#111827]'
                  }`}
                >
                  <div className="flex flex-col min-w-0 pr-4">
                    <span className="font-semibold text-sm text-white truncate num">
                      {item.symbol}
                    </span>
                    <span className="text-xs text-[#64748b] truncate">
                      {item.description}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-[#1e2d40] text-[#a2b8cc] rounded">
                      {item.exchange}
                    </span>
                    <span
                      className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${
                        item.type === 'FUT'
                          ? 'bg-[#8b5cf6]/20 text-[#a78bfa]'
                          : 'bg-[#14b8a6]/20 text-[#2dd4bf]'
                      }`}
                    >
                      {item.type}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
