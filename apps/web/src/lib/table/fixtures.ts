/**
 * Deterministic dummy data for table view test harness (e.g. ?fixture=1).
 * Used by Playwright tests and by the table popup when opened with fixture param.
 */

import type { ProductMeta } from "$lib/search/protocol";

export const TABLE_FIXTURE_PRODUCTS: ProductMeta[] = [
  {
    globalId: "2O2Fr$t4X7Zf8NO2L3bQpE",
    ifcClass: "IfcWall",
    name: "Wall-001",
    description: "Exterior wall segment",
    objectType: "Wall",
    tag: "W-01",
  },
  {
    globalId: "3P3Gs$u5Y8Ag9OP3M4cRqF",
    ifcClass: "IfcSlab",
    name: "Slab-Ground",
    description: "Ground floor slab",
    objectType: "Slab",
    tag: "S-01",
  },
  {
    globalId: "4Q4Ht$v6Z9Bh0PQ4N5dSrG",
    ifcClass: "IfcColumn",
    name: "Column-A1",
    description: null,
    objectType: "Column",
    tag: "C-01",
  },
  {
    globalId: "5R5Iu$w7A0Ci1QR5O6eTsH",
    ifcClass: "IfcWall",
    name: "Wall-002",
    description: "Internal partition",
    objectType: "Partition",
    tag: "W-02",
  },
  {
    globalId: "6S6Jv$x8B1Dj2RS6P7fUtI",
    ifcClass: "IfcDoor",
    name: "Door-Main",
    description: "Main entrance",
    objectType: "Door",
    tag: "D-01",
  },
];
