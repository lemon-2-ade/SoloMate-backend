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

-- AlterTable
ALTER TABLE "users" ADD COLUMN     "age" INTEGER,
ADD COLUMN     "gender" TEXT,
ADD COLUMN     "name" TEXT;

-- CreateIndex
CREATE UNIQUE INDEX "_QuestBadgeRewards_AB_unique" ON "_QuestBadgeRewards"("A", "B");

-- CreateIndex
CREATE UNIQUE INDEX "_UserFriends_AB_unique" ON "_UserFriends"("A", "B");
