/**
 * 元件庫的單一入口 — V2升級計畫 11 §3。
 *
 * 頁面一律從這裡取用，不要深入到個別檔案；之後拆檔或改名才不會動到呼叫端。
 *
 */

export { Button, type ButtonProps } from "./button";
export {
  Badge,
  type BadgeProps,
  type BadgeTone,
  checkInTone,
  paymentTone,
  claimTone,
  caseTone,
} from "./badge";
export { Card, CardHeader, CardBody, Tabs } from "./card";
export { DataTable, type Column } from "./data-table";
export { Field, Input, Select, Textarea } from "./field";
export { Modal, Drawer, type ModalProps } from "./modal";
export { StatBar, FilterBar, type Stat } from "./stat-bar";
export { Money, MoneySplit, CaseRef, QuotaBar } from "./domain";
export {
  TimeGrid,
  minutesOfDay,
  type TimeGridColumn,
  type TimeGridItem,
} from "./time-grid";
export { RoomCell, cellPhase, type RoomCellAppointment } from "./room-cell";
export {
  AsyncBoundary,
  EmptyState,
  ErrorState,
  Skeleton,
  TableSkeleton,
} from "./feedback";
