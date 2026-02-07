"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

type Tab = {
  id: string;
  label: string;
  icon?: React.ReactNode;
};

export const Tabs = ({
  tabs,
  activeTab,
  onTabChange,
  containerClassName,
  tabClassName,
  activeTabClassName,
}: {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  containerClassName?: string;
  tabClassName?: string;
  activeTabClassName?: string;
}) => {
  return (
    <div
      className={cn(
        "flex flex-row items-center justify-start relative overflow-auto scrollbar-hide max-w-full",
        containerClassName
      )}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={cn(
            "relative px-4 py-2 rounded-full text-sm font-medium transition-colors duration-200",
            tabClassName,
            activeTab === tab.id
              ? "text-white"
              : "text-white/60 hover:text-white/80"
          )}
        >
          {activeTab === tab.id && (
            <motion.div
              layoutId="active-tab-pill"
              className={cn(
                "absolute inset-0 bg-gradient-to-r from-blue-500/20 to-violet-500/20 rounded-full ring-1 ring-white/20",
                activeTabClassName
              )}
              transition={{ type: "spring", bounce: 0.3, duration: 0.6 }}
            />
          )}
          <span className="relative z-10 flex items-center gap-2">
            {tab.icon}
            {tab.label}
          </span>
        </button>
      ))}
    </div>
  );
};

export const AnimatedTabs = ({
  tabs,
  containerClassName,
  tabContentClassName,
}: {
  tabs: { id: string; label: string; content: React.ReactNode }[];
  containerClassName?: string;
  tabContentClassName?: string;
}) => {
  const [activeTab, setActiveTab] = useState(tabs[0]?.id ?? "");

  return (
    <div className={cn("w-full", containerClassName)}>
      <div className="flex items-center gap-2 p-1 bg-white/5 rounded-2xl ring-1 ring-white/10 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "relative px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200",
              activeTab === tab.id
                ? "text-white"
                : "text-white/50 hover:text-white/70"
            )}
          >
            {activeTab === tab.id && (
              <motion.div
                layoutId="animated-tab-bubble"
                className="absolute inset-0 bg-gradient-to-r from-blue-500/30 to-violet-500/30 rounded-xl ring-1 ring-white/20 shadow-lg"
                transition={{ type: "spring", bounce: 0.25, duration: 0.5 }}
              />
            )}
            <span className="relative z-10">{tab.label}</span>
          </button>
        ))}
      </div>

      <motion.div
        key={activeTab}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.3 }}
        className={cn("mt-6", tabContentClassName)}
      >
        {tabs.find((tab) => tab.id === activeTab)?.content}
      </motion.div>
    </div>
  );
};
