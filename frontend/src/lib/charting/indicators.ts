export function calculateSMA(data: any[], period: number = 14) {
  const result: any[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) continue;
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j].close;
    }
    result.push({ time: data[i].time, value: sum / period });
  }
  return result;
}

export function calculateEMA(data: any[], period: number = 14) {
  const result: any[] = [];
  const k = 2 / (period + 1);
  let ema = data[0]?.close || 0;
  for (let i = 0; i < data.length; i++) {
    if (i === 0) continue;
    ema = data[i].close * k + ema * (1 - k);
    if (i >= period - 1) {
      result.push({ time: data[i].time, value: ema });
    }
  }
  return result;
}

export function calculateVWAP(data: any[]) {
  const result: any[] = [];
  let cumVol = 0;
  let cumVolPrice = 0;
  for (let i = 0; i < data.length; i++) {
    const typicalPrice = (data[i].high + data[i].low + data[i].close) / 3;
    const vol = data[i].volume || 1;
    cumVol += vol;
    cumVolPrice += typicalPrice * vol;
    result.push({ time: data[i].time, value: cumVolPrice / cumVol });
  }
  return result;
}

export function calculateBollingerBands(data: any[], period: number = 20, multiplier: number = 2) {
  const upper: any[] = [];
  const lower: any[] = [];
  const basis = calculateSMA(data, period);
  
  const basisMap = new Map(basis.map(b => [b.time, b.value]));

  for (let i = period - 1; i < data.length; i++) {
    const time = data[i].time;
    const sma = basisMap.get(time);
    if (sma === undefined) continue;

    let variance = 0;
    for (let j = 0; j < period; j++) {
      variance += Math.pow(data[i - j].close - sma, 2);
    }
    const stdDev = Math.sqrt(variance / period);
    
    upper.push({ time, value: sma + stdDev * multiplier });
    lower.push({ time, value: sma - stdDev * multiplier });
  }
  
  return { upper, lower, basis };
}
