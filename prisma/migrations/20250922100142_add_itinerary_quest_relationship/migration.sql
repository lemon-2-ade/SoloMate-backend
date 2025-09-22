-- AlterTable
ALTER TABLE "public"."quests" ADD COLUMN     "itineraryId" TEXT;

-- AddForeignKey
ALTER TABLE "public"."quests" ADD CONSTRAINT "quests_itineraryId_fkey" FOREIGN KEY ("itineraryId") REFERENCES "public"."itineraries"("id") ON DELETE SET NULL ON UPDATE CASCADE;
