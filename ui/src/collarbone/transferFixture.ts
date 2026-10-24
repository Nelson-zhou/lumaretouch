// Synthetic DTO fixture only; not a rendered quality or execution claim.
import type {PeopleTransferReview} from '../people/transferProof';
import type {CollarboneVisual} from './transferModel';
export function visualFixture(review:PeopleTransferReview):CollarboneVisual{
  const image={mime:'image/png' as const,width:1,height:1,sha256:'1'.repeat(64)};
  return {version:1,document_id:review.target_document.document_id,revision:String(review.target_document.revision),source_proof:review.target_owner.source_proof,
    before_state_sha256:'2'.repeat(64),candidate_state_sha256:'3'.repeat(64),before_people_sha256:'4'.repeat(64),candidate_people_sha256:'5'.repeat(64),
    source_size:[1,1],before_output_size:[1,1],after_output_size:[1,1],coverage_sha256:'6'.repeat(64),before:image,after:{...image,sha256:'7'.repeat(64)}};
}
