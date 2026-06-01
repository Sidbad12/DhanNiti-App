'use client';

import dynamic from 'next/dynamic';

const ChartLayout = dynamic(
  () => import('@/components/charts/ChartLayout'),
  { ssr: false }
);

export default function ChartsPage() {
  return (
    <main className="w-full h-screen overflow-hidden">
      <ChartLayout />
    </main>
  );
}
