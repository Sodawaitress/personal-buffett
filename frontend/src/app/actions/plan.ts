"use server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { revalidatePath } from "next/cache";

export type PhaseType = "work" | "break" | "fire";

export interface Phase {
  id: string;
  type: PhaseType;
  label?: string;
  cityId?: string;
  cityName?: string;
  months: number;
  salaryCNY?: number;   // work only
  livingCNY: number;
  investRate: number;   // annual %, default 7.5
}

async function requireUser() {
  const session = await auth();
  if (!session?.user?.id) throw new Error("Not authenticated");
  return session.user.id;
}

export async function loadPlan(): Promise<Phase[]> {
  const userId = await requireUser();
  const record = await prisma.lifePlan.findUnique({ where: { userId } });
  if (!record) return [];
  try {
    return JSON.parse(record.phases) as Phase[];
  } catch {
    return [];
  }
}

export async function savePlan(phases: Phase[]): Promise<void> {
  const userId = await requireUser();
  await prisma.lifePlan.upsert({
    where:  { userId },
    update: { phases: JSON.stringify(phases) },
    create: { userId, phases: JSON.stringify(phases) },
  });
  revalidatePath("/tools/plan");
}
