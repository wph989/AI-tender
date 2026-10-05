import { notFound } from "next/navigation";
import { KnowledgeCollectionDetail } from "@/components/knowledge/KnowledgeCollectionDetail";

export default async function CollectionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const collectionId = Number(id);
  if (!Number.isSafeInteger(collectionId) || collectionId < 1) notFound();
  return <KnowledgeCollectionDetail key={collectionId} collectionId={collectionId} />;
}
