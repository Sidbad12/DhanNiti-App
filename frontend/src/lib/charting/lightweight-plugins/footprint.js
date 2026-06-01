// @ts-nocheck
// --- Footprint Chart Plugin - Tick Size Based Implementation ---
import { positionsLine, positionsBox, drawRoundedCandle, isValidOHLCData } from './chart-utils.js';

/**
 * Footprint Renderer - Renders footprint cells based on actual tick size
 * Each cell represents exactly one tick size increment (tick_size * multiplier)
 */
class FootprintRenderer {
    constructor() {
        this._data = null;
        this._options = null;
        this._textCache = new Map();
        this._font10 = '10px -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif';
        this._font9 = '9px -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif';
        this._maxCacheSize = 200;
        this._cotCache = new Map();
        this._lastVisibleRange = null;
    }

    draw(target, priceToCoordinate) {
        target.useBitmapCoordinateSpace(scope => this._drawImpl(scope, priceToCoordinate));
    }

    update(data, options) {
        this._data = data;
        this._options = options;

        // Manage cache size for memory efficiency
        if (this._textCache.size > this._maxCacheSize) {
            const entries = Array.from(this._textCache.entries());
            const toKeep = entries.slice(-Math.floor(this._maxCacheSize / 2));
            this._textCache.clear();
            toKeep.forEach(([key, value]) => this._textCache.set(key, value));
        }
    }

    _drawImpl(scope, priceToCoordinate) {
        console.log('[Footprint] _drawImpl called', { 
            hasData: !!this._data, 
            barsLen: this._data?.bars?.length, 
            hasVisibleRange: !!this._data?.visibleRange,
            hasOptions: !!this._options
        });
        const d = this._data;
        if (!d?.bars?.length || !d.visibleRange || !this._options) return;

        const ctx = scope.context;
        const { from, to } = d.visibleRange;
        const barSpacing = d.barSpacing;
        
        if (Math.random() < 0.05) {
            const sampleBar = d.bars[from];
            console.log('[Footprint] Debug:', { 
                spacing: barSpacing, 
                from, 
                to, 
                hasFP: !!sampleBar?.originalData?.footprint,
                fpLen: sampleBar?.originalData?.footprint?.length
            });
        }

        // Use simple candlesticks for very small spacing
        if (barSpacing < 6) {
            this._drawCandles(ctx, priceToCoordinate, scope, from, to);
            return;
        }

        ctx.save();
        ctx.imageSmoothingEnabled = false;

        try {
            for (let i = from; i < to; ++i) {
                const bar = d.bars[i];
                if (bar?.originalData && isValidOHLCData(bar.originalData)) {
                    this._drawBar(ctx, bar, priceToCoordinate, scope, barSpacing, i);
                }
            }
        } finally {
            ctx.restore();
        }
    }

    _drawCandles(ctx, priceToCoordinate, scope, from, to) {
        const { horizontalPixelRatio: h, verticalPixelRatio: v } = scope;

        for (let i = from; i < to; ++i) {
            const bar = this._data.bars[i];
            if (!bar?.originalData || !isValidOHLCData(bar.originalData)) continue;

            const d = bar.originalData;
            const x = bar.x;
            const openY = priceToCoordinate(d.open);
            const closeY = priceToCoordinate(d.close);
            const highY = priceToCoordinate(d.high);
            const lowY = priceToCoordinate(d.low);

            if ([openY, closeY, highY, lowY].some(Number.isNaN)) continue;

            const isUp = d.close >= d.open;
            ctx.fillStyle = isUp ? this._options.upColor : this._options.downColor;
            ctx.fillRect(Math.round(x * h), Math.min(openY, closeY) * v, 1, Math.abs(closeY - openY) * v || 1);

            if (this._options.wickVisible) {
                ctx.fillStyle = isUp ? this._options.wickUpColor : this._options.wickDownColor;
                ctx.fillRect(Math.round(x * h), Math.min(highY, lowY) * v, 1, Math.abs(lowY - highY) * v || 1);
            }
        }
    }

    _drawBar(ctx, bar, priceToCoordinate, scope, barSpacing, barIndex) {
        const { originalData: d, x } = bar;
        const bodyW = Math.max(2, Math.min(12, barSpacing * 0.8));

        this._drawCandle(ctx, d, x, bodyW, priceToCoordinate, scope);

        const hasFootprint = Array.isArray(d.footprint) && d.footprint.length;

        // Draw Footprint Cells if zoomed in enough (high resolution)
        if (barSpacing >= 20 && hasFootprint) {
            const fpW = this._footprintWidth(ctx, d.footprint);
            this._drawFootprintCells(ctx, d, x + bodyW / 2 + 4, fpW, priceToCoordinate, scope, barIndex);
        }

        // Draw Aggressive Bubbles overlay (Big Trade Hunter) - independent of zoom
        if (hasFootprint && this._options.showBubbles !== false) {
            // Center bubbles on the candle body
            const startX = x; 
            // Draw bubbles with 0 offset (centered on x)
            this._drawAggressiveBubbles(ctx, d.footprint, startX, 0, priceToCoordinate, scope);
        }
    }

    _drawCandle(ctx, d, x, w, priceToCoordinate, scope) {
        drawRoundedCandle(ctx, d, x, w, priceToCoordinate, scope, this._options);
    }

    _footprintWidth(ctx, footprint) {
        const key = footprint.map(f => `${f.buyVolume}x${f.sellVolume}`).join('|');
        if (this._textCache.has(key)) return this._textCache.get(key);

        ctx.font = this._font10;
        let maxW = 0;

        for (const f of footprint) {
            const txt = this._formatVolumeText(f.buyVolume, f.sellVolume, f.buyVolume - f.sellVolume);
            maxW = Math.max(maxW, ctx.measureText(txt).width);
        }

        const fpW = Math.max(36, Math.ceil(maxW) + 10);
        this._textCache.set(key, fpW);
        return fpW;
    }

    /**
     * Draw footprint cells based on actual tick size
     * Each cell height represents exactly one tick size increment (tick_size * multiplier)
     */
    _drawFootprintCells(ctx, d, startX, width, priceToCoordinate, scope, barIndex) {
        const { horizontalPixelRatio: h, verticalPixelRatio: v } = scope;
        const fp = Array.isArray(d.footprint) ? [...d.footprint].sort((a, b) => b.priceLevel - a.priceLevel) : [];
        if (!fp.length) return;

        // Get tick size from options - this is the effective bucket size (tick_size * multiplier)
        const effectiveTickSize = this._options.tickSize || 5.0; // Default fallback
        
        ctx.font = this._font9;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        // Color gradients
        const downGradient = this._options.downGradientColors || [
            '#F08090', '#D94A5A', '#A12A3A', '#3B0D16'
        ];
        const upGradient = this._options.upGradientColors || [
            '#5FE1C5', '#2FC1A2', '#007C65', '#00332A'
        ];
        const neutralColor = this._options.neutralColor || '#B2B5BE';

        // Calculate volume-based coloring
        const volumes = fp.map(f => (f.buyVolume || 0) + (f.sellVolume || 0));
        const maxVol = Math.max(...volumes);
        const minVol = Math.min(...volumes);
        const volRange = maxVol - minVol || 1;

        const cellGeometry = new Map();
        const xPosStatic = positionsLine(startX + width / 2, h, width);

        // Draw each footprint cell based on tick size
        for (let i = 0; i < fp.length; ++i) {
            const f = fp[i];
            const priceLevel = f.priceLevel;

            // Calculate cell boundaries based on tick size
            const cellBottomPrice = priceLevel; 
            const cellTopPrice = priceLevel + effectiveTickSize; 

            // Convert price boundaries to pixel coordinates
            const cellBottom = priceToCoordinate(cellBottomPrice); 
            const cellTop = priceToCoordinate(cellTopPrice); 

            if ([cellTop, cellBottom, priceLevel].some(Number.isNaN)) continue;

            const buy = f.buyVolume || 0;
            const sell = f.sellVolume || 0;
            const total = buy + sell;
            const delta = buy - sell;

            // Calculate cell position and size
            const xPos = xPosStatic;
            const yPos = positionsBox(cellTop, cellBottom, v);
            
            // Skip tiny cells but ensure we draw at least 1 pixel if zoomed enough
            if (yPos.length < 1) continue;

            // Determine cell color and transparency
            let bgColor, alpha;
            if (buy === 0 && sell === 0) {
                bgColor = this._options.lowVolumeColor || '#FFB433';
                alpha = 0.4; 
            } else if (!total) {
                bgColor = neutralColor;
                alpha = 0.1;
            } else if (buy < 99 || sell < 99) {
                const yellowLowVolumeColor = this._options.lowVolumeColor || '#FFB433';
                const minVolume = Math.min(buy, sell);
                const shouldHideYellowLowVolume = document.body.classList.contains('hide-low-volume');
                if (shouldHideYellowLowVolume) {
                    const ratio = (total - minVol) / volRange;
                    const grad = delta >= 0 ? upGradient : downGradient;
                    const idx = Math.min(grad.length - 1, Math.floor(ratio * grad.length));
                    bgColor = grad[idx];
                    alpha = 0.3 + Math.min(1, Math.abs(delta / (total || 1))) * 0.3;
                } else {
                    bgColor = yellowLowVolumeColor;
                    alpha = Math.max(0.3, 0.7 - (minVolume / 99) * 0.3);
                }
            } else {
                const ratio = (total - minVol) / volRange;
                const grad = delta >= 0 ? upGradient : downGradient;
                const idx = Math.min(grad.length - 1, Math.floor(ratio * grad.length));
                bgColor = grad[idx];
                alpha = Math.min(0.8, 0.35 + Math.min(1, Math.abs(delta / (total || 1))) * 0.45);
            }

            // Draw cell background
            ctx.globalAlpha = alpha;
            ctx.fillStyle = bgColor;

            // Rounded corners for boundary cells
            const radius = Math.min(3, Math.min(xPos.length, yPos.length) * 0.15);

            if (radius > 1 && (i === 0 || i === fp.length - 1)) {
                ctx.beginPath();
                if (i === 0) ctx.roundRect(xPos.position, yPos.position, xPos.length, yPos.length, [radius, radius, 0, 0]);
                else ctx.roundRect(xPos.position, yPos.position, xPos.length, yPos.length, [0, 0, radius, radius]);
                ctx.fill();
            } else {
                ctx.fillRect(xPos.position, yPos.position, xPos.length, yPos.length);
            }

            // Draw border for all cells for better definition
            ctx.globalAlpha = 0.2;
            ctx.strokeStyle = this._options.cellBorderColor || '#333';
            ctx.lineWidth = 0.5 * h;
            ctx.strokeRect(xPos.position, yPos.position, xPos.length, yPos.length);

            // Draw volume text if cell is large enough
            if (xPos.length >= 24 && yPos.length >= 10) {
                ctx.globalAlpha = 1;
                ctx.fillStyle = this._options.textColor || '#fff';
                ctx.fillText(
                    this._formatVolumeText(buy, sell, delta),
                    xPos.position + xPos.length / 2,
                    yPos.position + yPos.length / 2
                );
            }

            // Store cell geometry for indicators
            cellGeometry.set(priceLevel, {
                top: yPos.position,
                bottom: yPos.position + yPos.length,
                center: yPos.position + yPos.length / 2,
                height: yPos.length,
                priceLevel: priceLevel
            });
        }

        // Draw additional features
        if (this._options.showCOT !== false) {
            this._drawCOTMarkers(ctx, d, fp, startX, width, priceToCoordinate, scope, cellGeometry, xPosStatic, barIndex);
        }

        if (this._options.showImbalance !== false) {
            this._drawImbalanceIndicators(ctx, fp, startX, width, priceToCoordinate, scope, cellGeometry, xPosStatic);
        }

        // Bubbles are drawn separately in _drawBar

        if (this._options.showTable !== false && (d.volume || d.delta !== undefined)) {
            this._drawSummaryTable(ctx, d, startX, width, priceToCoordinate(d.low), scope, priceToCoordinate);
        }
    }

    _drawAggressiveBubbles(ctx, fp, startX, width, priceToCoordinate, scope) {
        const { horizontalPixelRatio: h, verticalPixelRatio: v } = scope;
        // Threshold for "Aggressive" trade (e.g. > 50k lots)
        const threshold = this._options.bubbleThreshold || 50000; 
        
        // Ensure absolute minimum radius of 3px for visibility at any zoom
        const minRadiusAbs = 3;
        const minRadius = Math.max(minRadiusAbs, 4 * h); 
        const maxRadius = 25 * h;
        
        // Center of the bar in pixels (startX is already the center x coordinate)
        const centerX = startX * h;

        for (const f of fp) {
            const totalVol = (f.buyVolume || 0) + (f.sellVolume || 0);
            if (totalVol < threshold) continue;

            const buy = f.buyVolume || 0;
            const sell = f.sellVolume || 0;
            const delta = buy - sell;
            
            // Determine color based on Delta dominance
            // Green if Buy > Sell, Red if Sell > Buy
            const isBuyDominated = delta > 0;
            
            const color = isBuyDominated 
                ? (this._options.bubbleUpColor || 'rgba(0, 200, 83, 0.4)') 
                : (this._options.bubbleDownColor || 'rgba(255, 23, 68, 0.4)');
            
            const borderColor = isBuyDominated 
                ? (this._options.bubbleUpBorder || '#00C853') 
                : (this._options.bubbleDownBorder || '#FF1744');

            // Scale radius log-linearly based on excess volume over threshold
            // base + log(vol/threshold) * scale
            const scale = Math.log(totalVol / threshold + 1) * 8 * h;
            const radius = Math.min(maxRadius, Math.max(minRadius, scale));

            const y = priceToCoordinate(f.priceLevel + (this._options.tickSize || 0.05)/2) * v; // Centered in tick

            ctx.beginPath();
            ctx.arc(centerX, y, radius, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.globalAlpha = 0.6; // Ensure visibility
            ctx.fill();
            
            ctx.lineWidth = 1.5 * h;
            ctx.strokeStyle = borderColor;
            ctx.globalAlpha = 1.0;
            ctx.stroke();
            
            // Optional: Draw volume text inside if big enough
            if (radius > 10 * h) {
                ctx.fillStyle = '#fff';
                ctx.font = `bold ${Math.round(radius * 0.8)}px sans-serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                // Show K notation
                const volTxt = totalVol >= 1000 ? (totalVol/1000).toFixed(1) + 'k' : totalVol;
                ctx.fillText(volTxt, centerX, y);
            }
        }
    }

    _drawImbalanceIndicators(ctx, fp, startX, width, priceToCoordinate, scope, cellGeometry, xPosStatic) {
        const { horizontalPixelRatio: h, verticalPixelRatio: v } = scope;
        const imbalanceThreshold = this._options.imbalanceThreshold || 300;
        const severeImbalanceThreshold = this._options.severeImbalanceThreshold || 500;
        const severeImbalanceColor = this._options.severeImbalanceColor || '#FFB433';
        const imbalanceMarkerAlpha = this._options.imbalanceMarkerAlpha || 1.0;
        const markerSize = this._options.imbalanceMarkerSize || 6;
        const lineLength = markerSize;

        if (fp.length < 2) return;

        const sortedFp = [...fp].sort((a, b) => a.priceLevel - b.priceLevel);
        ctx.lineWidth = 1;
        ctx.globalAlpha = imbalanceMarkerAlpha;

        const rightX = (xPosStatic.position + xPosStatic.length + 1);
        const leftX = (xPosStatic.position - 2);

        // Buy imbalance markers (right side)
        for (let i = 1; i < sortedFp.length; i++) {
            if (i - 1 === 0) continue;
            const cur = sortedFp[i];
            const lower = sortedFp[i - 1];
            const curBuy = cur.buyVolume || 0;
            const lowerSell = lower.sellVolume || 0;

            if (this._detectImbalance(curBuy, lowerSell, imbalanceThreshold)) {
                const geom = cellGeometry.get(cur.priceLevel);
                if (geom) {
                    const isSevere = this._detectImbalance(curBuy, lowerSell, severeImbalanceThreshold);
                    ctx.strokeStyle = isSevere ? severeImbalanceColor : (this._options.imbalanceColor || '#8cc7a1');
                    ctx.beginPath();
                    ctx.moveTo(rightX * h, geom.center * v - (lineLength / 2) * v);
                    ctx.lineTo(rightX * h, geom.center * v + (lineLength / 2) * v);
                    ctx.stroke();
                }
            }
        }

        // Sell imbalance markers (left side)
        for (let i = 0; i < sortedFp.length - 1; i++) {
            const cur = sortedFp[i];
            const higher = sortedFp[i + 1];
            const curSell = cur.sellVolume || 0;
            const higherBuy = higher.buyVolume || 0;

            if (this._detectImbalance(curSell, higherBuy, imbalanceThreshold)) {
                const geom = cellGeometry.get(cur.priceLevel);
                if (geom) {
                    const isSevere = this._detectImbalance(curSell, higherBuy, severeImbalanceThreshold);
                    ctx.strokeStyle = isSevere ? severeImbalanceColor : (this._options.imbalanceColor || '#8cc7a1');
                    ctx.beginPath();
                    ctx.moveTo(leftX * h, geom.center * v - (lineLength / 2) * v);
                    ctx.lineTo(leftX * h, geom.center * v + (lineLength / 2) * v);
                    ctx.stroke();
                }
            }
        }
        ctx.globalAlpha = 1;
    }

    _detectImbalance(largerVolume, smallerVolume, thresholdPercent) {
        if (smallerVolume === 0) return largerVolume > 0;
        return largerVolume >= (thresholdPercent / 100) * smallerVolume;
    }

    _drawCOTMarkers(ctx, d, fp, startX, width, priceToCoordinate, scope, cellGeometry, xPosStatic, barIndex) {
        const { horizontalPixelRatio: h, verticalPixelRatio: v } = scope;

        const cotData = this._calculateCOT(d, fp, barIndex);
        const { cotHigh, cotLow } = cotData;

        const markerSize = this._options.cotMarkerSize || 8;
        const markerOffset = this._options.cotMarkerOffset || 12;

        ctx.save();
        ctx.globalAlpha = this._options.cotMarkerAlpha || 0.9;

        const sortedFp = [...fp].sort((a, b) => b.priceLevel - a.priceLevel);
        const highestFpLevel = sortedFp[0]?.priceLevel;
        const lowestFpLevel = sortedFp[sortedFp.length - 1]?.priceLevel;

        // Store COT bottom pixel boundary for table positioning
        let cotBottomPixelBoundary = null;

        // Draw COT High marker
        if (highestFpLevel !== undefined) {
            const geom = cellGeometry.get(highestFpLevel);
            if (geom) {
                const markerY = geom.top - markerOffset;
                const markerX = xPosStatic.position + xPosStatic.length / 2;

                ctx.fillStyle = cotHigh === 0 ? (this._options.cotZeroColor || '#FFB433') :
                                 (cotHigh > 0 ? (this._options.cotHighColor || '#00C853') :
                                  (this._options.cotLowColor || '#FF1744'));

                const mx = markerX * h;
                const my = markerY * v;
                const halfW = (markerSize / 2) * h;
                const vert = markerSize * v;

                ctx.beginPath();
                if (cotHigh >= 0) {
                    ctx.moveTo(mx, my);
                    ctx.lineTo(mx - halfW, my + vert);
                    ctx.lineTo(mx + halfW, my + vert);
                } else {
                    ctx.moveTo(mx, my + vert);
                    ctx.lineTo(mx - halfW, my);
                    ctx.lineTo(mx + halfW, my);
                }
                ctx.closePath();
                ctx.fill();

                // Draw COT High label
                ctx.globalAlpha = this._options.cotMarkerAlpha || 0.9;
                ctx.fillStyle = this._options.textColor || '#fff';
                ctx.font = this._font9;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';
                const cotText = `CH ${cotHigh >= 0 ? '+' : ''}${this._formatDelta(cotHigh)}`;
                const labelPad = this._options.cotLabelPadding || 6;
                ctx.fillText(cotText, mx, my - labelPad);
            }
        }

        // Draw COT Low marker
        if (lowestFpLevel !== undefined) {
            const geom = cellGeometry.get(lowestFpLevel);
            if (geom) {
                const markerY = geom.bottom + markerOffset;
                const markerX = xPosStatic.position + xPosStatic.length / 2;

                // Store the bottom boundary for table positioning (in pixel coordinates)
                const mx = markerX * h;
                const my = markerY * v;
                const halfW = (markerSize / 2) * h;
                const vert = markerSize * v;

                ctx.fillStyle = cotLow === 0 ? (this._options.cotZeroColor || '#FFB433') :
                                 (cotLow > 0 ? (this._options.cotHighColor || '#00C853') :
                                  (this._options.cotLowColor || '#FF1744'));

                ctx.beginPath();
                if (cotLow >= 0) {
                    ctx.moveTo(mx, my - vert);
                    ctx.lineTo(mx - halfW, my);
                    ctx.lineTo(mx + halfW, my);
                } else {
                    ctx.moveTo(mx, my + vert);
                    ctx.lineTo(mx - halfW, my);
                    ctx.lineTo(mx + halfW, my);
                }
                ctx.closePath();
                ctx.fill();

                // Draw COT Low label
                ctx.globalAlpha = this._options.cotMarkerAlpha || 0.9;
                ctx.fillStyle = this._options.textColor || '#fff';
                ctx.font = this._font9;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';
                const cotText = `CL ${cotLow >= 0 ? '+' : ''}${this._formatDelta(cotLow)}`;
                const labelPad = this._options.cotLabelPadding || 6;
                const labelY = my + vert + labelPad;
                ctx.fillText(cotText, mx, labelY);

                // Calculate bottom boundary including label (in pixel coordinates)
                cotBottomPixelBoundary = labelY + 12; // 12 pixels for approximate text height
            }
        }

        // Store COT boundary information for use by other drawing functions
        this._cotBottomPixelBoundary = cotBottomPixelBoundary;

        ctx.restore();
    }

    _calculateCOT(d, fp, barIndex) {
        if (!fp || !fp.length || !d) return { cotHigh: 0, cotLow: 0, hasNewHigh: false, hasNewLow: false };

        const high = d.high;
        const low = d.low;
        const close = d.close;

        const sortedFp = [...fp].sort((a, b) => b.priceLevel - a.priceLevel);

        let cotHigh = 0;
        let cotLow = 0;

        // COT High: accumulate delta from high down to close
        for (const level of sortedFp) {
            if (level.priceLevel <= high && level.priceLevel >= close) {
                const delta = (level.buyVolume || 0) - (level.sellVolume || 0);
                cotHigh += delta;
            }
        }

        // COT Low: accumulate delta from low up to close
        for (const level of sortedFp) {
            if (level.priceLevel >= low && level.priceLevel <= close) {
                const delta = (level.buyVolume || 0) - (level.sellVolume || 0);
                cotLow += delta;
            }
        }

        return {
            cotHigh,
            cotLow,
            hasNewHigh: false,
            hasNewLow: false
        };
    }

    _drawSummaryTable(ctx, d, startX, width, lowY, scope, priceToCoordinate) {
        const { horizontalPixelRatio: h, verticalPixelRatio: v } = scope;
        const showCumul = this._options?.showCumulative !== false;
        const tableHeight = showCumul ? 48 : 28;

        // Position table using pixel coordinates with proper spacing from COT
        let tableY;
        if (this._options.showCOT !== false && this._cotBottomPixelBoundary !== null) {
            // Position table below COT markers with small buffer
            tableY = this._cotBottomPixelBoundary + 8; // 8 pixels buffer
        } else {
            // Position table below the lowest footprint level
            tableY = lowY + 10;
        }

        ctx.globalAlpha = 0.9;
        ctx.fillStyle = this._options.tableBackgroundColor || '#1E222D';
        const xPos = positionsLine(startX + width / 2, h, width);
        const yPos = positionsBox(tableY, tableY + tableHeight, v);
        const radius = 3;

        ctx.beginPath();
        ctx.roundRect(xPos.position, yPos.position, xPos.length, yPos.length, radius);
        ctx.fill();

        ctx.globalAlpha = 1;
        ctx.strokeStyle = this._options.tableBorderColor || '#2A2E39';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.font = this._font9;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        const tableRows = showCumul ? 3 : 2;
        const centerX = xPos.position + xPos.length / 2;
        const lineHeight = (yPos.length - 8) / tableRows;
        const startY = yPos.position + 4 + lineHeight / 2;

        ctx.fillStyle = this._options.textColor || '#fff';
        ctx.fillText(`Vol: ${this._formatNum(d.volume || 0)}`, centerX, startY);

        const delta = d.delta || 0;
        ctx.fillStyle = delta >= 0 ? this._options.upColor : this._options.downColor;
        ctx.fillText(`Δ ${this._formatDelta(Math.abs(delta))}`, centerX, startY + lineHeight);

        if (showCumul) {
            const cdVal = (d.cum_delta !== undefined) ? d.cum_delta : (d.cumDelta !== undefined ? d.cumDelta : 0);
            if (typeof cdVal === 'number') {
                if (cdVal > 0) ctx.fillStyle = this._options.upColor;
                else if (cdVal < 0) ctx.fillStyle = this._options.downColor;
                else ctx.fillStyle = this._options.tableTextColor || this._options.textColor || '#fff';
            } else {
                ctx.fillStyle = this._options.tableTextColor || this._options.textColor || '#fff';
            }
            ctx.fillText(`ΣΔ ${this._formatDelta(Math.abs(cdVal))}`, centerX, startY + lineHeight * 2);
        }
        ctx.globalAlpha = 1;
    }

    _formatNum(n) {
        if (typeof n !== 'number') n = Number(n) || 0;
        if (n < 1000) return n.toString();
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        return (n / 1e3).toFixed(1) + 'K';
    }

    _formatDelta(n) {
        if (typeof n !== 'number') n = Number(n) || 0;
        const trim = (s) => String(s).replace(/\.?0+$/, '');
        if (n < 1000) return trim(n.toFixed(2));
        if (n >= 1e6) return trim((n / 1e6).toFixed(2)) + 'M';
        return trim((n / 1e3).toFixed(2)) + 'K';
    }

    _formatVolumeText(buy, sell, delta) {
        switch (this._options.volumeDisplayMode) {
            case 'split': return `${this._formatNum(sell)}x${this._formatNum(buy)}`;
            case 'delta': return `${this._formatNum(Math.abs(delta))}`;
            case 'total': return this._formatNum(buy + sell);
            default: return `${this._formatNum(sell)}x${this._formatNum(buy)}`;
        }
    }
}

/**
 * Footprint Series - Tick Size Based Implementation
 */
export const FootprintSeries = {
    create() {
        return Object.create(this, {
            _renderer: { value: null, writable: true },
            _options: { value: null, writable: true },
            _defaultOptions: { value: null, writable: true }
        });
    },

    renderer() {
        if (!this._renderer) {
            this._renderer = new FootprintRenderer();
        }
        return this._renderer;
    },

    update(data, options) {
        if (!this._renderer) {
            this._renderer = new FootprintRenderer();
        }
        this._options = this._options ? Object.assign(this._options, options) : Object.assign({}, this.defaultOptions(), options);
        this._renderer.update(data, this._options);
    },

    priceValueBuilder(row) {
        if (!isValidOHLCData(row)) {
            return [0, 0, 0, 0];
        }
        return [row.open, row.high, row.low, row.close];
    },

    isWhitespace(row) {
        return !isValidOHLCData(row);
    },

    defaultOptions() {
        if (!this._defaultOptions) {
            this._defaultOptions = {
                // Candle colors
                upColor: '#089981',
                downColor: '#F23645',
                borderUpColor: '#089981',
                borderDownColor: '#F23645',
                wickUpColor: '#089981',
                wickDownColor: '#F23645',

                // Visibility settings
                borderVisible: true,
                wickVisible: true,

                // Footprint colors
                neutralColor: '#B2B5BE',
                cellBorderColor: '#333',
                textColor: '#fff',
                lowVolumeColor: '#FFB433',

                // Volume display
                volumeDisplayMode: 'split',
                visible: true,

                // Table settings
                showTable: true,
                tableBackgroundColor: '#1E222D',
                tableBorderColor: '#2A2E39',
                tableTextColor: '#B2B5BE',
                showCumulative: true,

                // Imbalance settings
                showImbalance: true,
                imbalanceThreshold: 300,
                imbalanceColor: '#BAD7E9',
                imbalanceMarkerAlpha: 1.0,
                imbalanceMarkerSize: 6,
                severeImbalanceThreshold: 500,
                severeImbalanceColor: '#FFB433',
                imbalanceVolumeThreshold: 2000,
                imbalanceAbsoluteColor: '#fca311',

                // COT (Commitment of Traders) settings
                showCOT: true,
                cotMarkerSize: 6,
                cotMarkerOffset: 16,
                cotLabelPadding: 6,
                cotMarkerAlpha: 0.9,
                cotHighColor: '#00C853',
                cotLowColor: '#FF1744',
                cotZeroColor: '#FFB433',
                cotThreshold: 10,

                // Aggressive Bubbles (Big Trade Hunter)
                showBubbles: true,
                bubbleThreshold: 50000, // Show bubbles for levels with > 50k volume (NIFTY optimized)
                bubbleUpColor: 'rgba(0, 200, 83, 0.3)',
                bubbleDownColor: 'rgba(255, 23, 68, 0.3)',
                bubbleUpBorder: '#00C853',
                bubbleDownBorder: '#FF1744',

                // Tick size setting - this is the effective bucket size (tick_size * multiplier)
                tickSize: 5.0, // Default effective bucket size (0.05 * 100)
            };
        }
        return this._defaultOptions;
    },

    applyOptions(options) {
        this._options = Object.assign({}, this._options || this.defaultOptions(), options);
        return this;
    },

    // Add method to handle low volume toggle events
    setupLowVolumeToggleListener() {
        document.addEventListener('lowVolumeMarkerToggled', () => {
            // Trigger chart re-render when low volume state changes
            if (window.chartRegistry && typeof window.selectedChartIndex === 'number') {
                const chartObj = window.chartRegistry[window.selectedChartIndex];
                if (chartObj && chartObj.chart && typeof chartObj.chart.requestAnimationFrame === 'function') {
                    chartObj.chart.requestAnimationFrame();
                }
            }
        });
    },

    destroy() {
        if (this._renderer?._textCache) {
            this._renderer._textCache.clear();
        }
        this._renderer = null;
        this._options = null;
        this._defaultOptions = null;

        // Remove low volume toggle listener
        document.removeEventListener('lowVolumeMarkerToggled', this.setupLowVolumeToggleListener);
    }
};