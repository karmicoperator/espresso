"use client";

import { cn } from "@/lib/utils";
import {
  AnimatePresence,
  MotionValue,
  motion,
  useMotionValue,
  useSpring,
  useTransform,
} from "framer-motion";
import { useRef, useState } from "react";

export const FloatingDock = ({
  items,
  activeId,
  onItemClick,
  className,
}: {
  items: { id: string; title: string; icon: React.ReactNode }[];
  activeId?: string;
  onItemClick?: (id: string) => void;
  className?: string;
}) => {
  const mouseX = useMotionValue(Infinity);
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      onMouseMove={(e) => mouseX.set(e.pageX)}
      onMouseLeave={() => mouseX.set(Infinity)}
      className={cn(
        "mx-auto flex h-16 gap-4 items-end rounded-2xl bg-[#141421]/90 backdrop-blur-xl px-4 pb-3 ring-1 ring-[#58c4dd]/20",
        className
      )}
    >
      {items.map((item) => (
        <IconContainer
          key={item.id}
          mouseX={mouseX}
          {...item}
          isActive={activeId === item.id}
          onClick={() => onItemClick?.(item.id)}
        />
      ))}
    </motion.div>
  );
};

function IconContainer({
  mouseX,
  title,
  icon,
  isActive,
  onClick,
}: {
  mouseX: MotionValue;
  title: string;
  icon: React.ReactNode;
  isActive?: boolean;
  onClick?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);

  const distance = useTransform(mouseX, (val) => {
    const bounds = ref.current?.getBoundingClientRect() ?? { x: 0, width: 0 };
    return val - bounds.x - bounds.width / 2;
  });

  const widthTransform = useTransform(distance, [-150, 0, 150], [40, 60, 40]);
  const heightTransform = useTransform(distance, [-150, 0, 150], [40, 60, 40]);

  const width = useSpring(widthTransform, {
    mass: 0.1,
    stiffness: 150,
    damping: 12,
  });
  const height = useSpring(heightTransform, {
    mass: 0.1,
    stiffness: 150,
    damping: 12,
  });

  return (
    <motion.div
      ref={ref}
      style={{ width, height }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      className={cn(
        "aspect-square rounded-xl flex items-center justify-center cursor-pointer relative transition-colors duration-200",
        isActive
          ? "bg-gradient-to-br from-[#58c4dd]/30 to-[#cd8b62]/30 ring-2 ring-[#58c4dd]/50"
          : "bg-[#1c1c2e] hover:bg-[#58c4dd]/20 ring-1 ring-[#58c4dd]/10"
      )}
    >
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, y: 10, x: "-50%" }}
            animate={{ opacity: 1, y: 0, x: "-50%" }}
            exit={{ opacity: 0, y: 2, x: "-50%" }}
            className="px-3 py-1.5 whitespace-pre rounded-lg bg-[#141421] border border-[#58c4dd]/20 text-[#f4f1eb] text-xs absolute left-1/2 -top-10"
          >
            {title}
          </motion.div>
        )}
      </AnimatePresence>
      <div className={cn(
        "transition-colors duration-200",
        isActive ? "text-[#58c4dd]" : "text-[#f4f1eb]/70"
      )}>
        {icon}
      </div>
    </motion.div>
  );
}
