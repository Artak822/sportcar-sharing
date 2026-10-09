import type * as React from 'react';

export type CarStatus = 'available' | 'booked' | 'service';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary — papaya, одна на экран; agent — только для подтверждения действия агента */
  variant?: 'primary' | 'secondary' | 'ghost' | 'agent';
  size?: 'md' | 'lg';
  block?: boolean;
}
export declare function Button(props: ButtonProps): React.ReactElement;

export interface BadgeProps {
  tone?: 'neutral' | CarStatus | 'agent';
  /** Без children статусы подписываются сами: «Свободен», «Занят», «На обслуживании» */
  children?: React.ReactNode;
}
export declare function Badge(props: BadgeProps): React.ReactElement;

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  /** Текст ошибки: заменяет hint и красит рамку в stop */
  error?: string;
}
export declare function Input(props: InputProps): React.ReactElement;

export interface CarCardProps {
  name: string;
  pricePerDay: number;
  status?: CarStatus;
  specs?: { power?: number; accel?: number; seats?: number };
  imageSrc?: string;
  onBook?: () => void;
}
export declare function CarCard(props: CarCardProps): React.ReactElement;

export interface SpecListProps {
  items: { label: string; value: React.ReactNode; unit?: string }[];
  /** На плите carbon */
  dark?: boolean;
}
export declare function SpecList(props: SpecListProps): React.ReactElement;

export interface BookingSummaryProps {
  car: string;
  from: string;
  to: string;
  days: number;
  pricePerDay: number;
  deposit?: number;
  extras?: { label: string; price: number }[];
  onConfirm?: () => void;
  confirmLabel?: string;
}
export declare function BookingSummary(props: BookingSummaryProps): React.ReactElement;

export interface AgentMessageProps {
  role?: 'agent' | 'user';
  time?: string;
  children?: React.ReactNode;
}
export declare function AgentMessage(props: AgentMessageProps): React.ReactElement;

export interface AgentActionProps {
  /** Имя MCP-инструмента, например create_booking */
  tool: string;
  title: string;
  status?: 'proposed' | 'running' | 'done' | 'failed';
  details?: { label: string; value: React.ReactNode }[];
  note?: string;
  confirmLabel?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
}
export declare function AgentAction(props: AgentActionProps): React.ReactElement;

declare global {
  interface Window {
    Pitlane: {
      Button: typeof Button; Badge: typeof Badge; Input: typeof Input; CarCard: typeof CarCard;
      SpecList: typeof SpecList; BookingSummary: typeof BookingSummary;
      AgentMessage: typeof AgentMessage; AgentAction: typeof AgentAction;
    };
  }
}
