/** 共享视图分类类型：Sidebar 与 App 共用。 */

export type FeedKind =
  | { kind: "all" }
  | { kind: "recent" }
  | { kind: "favorites" }
  | { kind: "dir"; dir: string | null; title: string };