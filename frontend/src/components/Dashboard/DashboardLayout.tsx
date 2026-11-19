import type { ReactNode } from 'react';
import { motion } from 'motion/react';

interface DashboardLayoutProps {
  header: ReactNode;
  topLeft: ReactNode;
  topCenter: ReactNode;
  topRight: ReactNode;
  middleLeft: ReactNode;
  middleCenter: ReactNode;
  middleRight: ReactNode;
  bottomLeft: ReactNode;
  bottomCenter: ReactNode;
  bottomRight: ReactNode;
  scanner: ReactNode;
  trades: ReactNode;
  footer: ReactNode;
}

export function DashboardLayout({
  header,
  topLeft,
  topCenter,
  topRight,
  middleLeft,
  middleCenter,
  middleRight,
  bottomLeft,
  bottomCenter,
  bottomRight,
  scanner,
  trades,
  footer,
}: DashboardLayoutProps) {
  return (
    <div className="alpaca-terminal relative flex-1 overflow-y-auto">
      <div className="relative z-[1] mx-auto max-w-[1600px] px-4 py-6 md:px-6 md:py-8">
        {header}

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.35 }}
          className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12"
        >
          <div className="xl:col-span-3">{topLeft}</div>
          <div className="xl:col-span-5">{topCenter}</div>
          <div className="xl:col-span-4">{topRight}</div>

          <div className="xl:col-span-4">{middleLeft}</div>
          <div className="xl:col-span-4">{middleCenter}</div>
          <div className="xl:col-span-4">{middleRight}</div>

          <div className="xl:col-span-5">{bottomLeft}</div>
          <div className="xl:col-span-3">{bottomCenter}</div>
          <div className="xl:col-span-4">{bottomRight}</div>
        </motion.div>

        <div className="mt-4">{trades}</div>
        <div className="mt-4">{scanner}</div>
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">{footer}</div>
      </div>
    </div>
  );
}
