/*
  Warnings:

  - The primary key for the `_QuestBadgeRewards` table will be changed. If it partially fails, the table could be left without primary key constraint.
  - The primary key for the `_UserFriends` table will be changed. If it partially fails, the table could be left without primary key constraint.
  - A unique constraint covering the columns `[A,B]` on the table `_QuestBadgeRewards` will be added. If there are existing duplicate values, this will fail.
  - A unique constraint covering the columns `[A,B]` on the table `_UserFriends` will be added. If there are existing duplicate values, this will fail.

*/
-- AlterTable
ALTER TABLE "_QuestBadgeRewards" DROP CONSTRAINT "_QuestBadgeRewards_AB_pkey";

-- AlterTable
ALTER TABLE "_UserFriends" DROP CONSTRAINT "_UserFriends_AB_pkey";

-- CreateTable
CREATE TABLE "journal_entries" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "date" TIMESTAMP(3) NOT NULL,
    "location" TEXT,
    "mood" TEXT,
    "tags" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "journal_entries_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "_QuestBadgeRewards_AB_unique" ON "_QuestBadgeRewards"("A", "B");

-- CreateIndex
CREATE UNIQUE INDEX "_UserFriends_AB_unique" ON "_UserFriends"("A", "B");

-- AddForeignKey
ALTER TABLE "journal_entries" ADD CONSTRAINT "journal_entries_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
