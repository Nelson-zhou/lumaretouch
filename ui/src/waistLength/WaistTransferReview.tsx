import {BodyScalarTransferReview,type BodyScalarReviewProps} from '../bodyScalar/BodyScalarTransferReview';
export function WaistTransferReview(props:BodyScalarReviewProps){
  return <BodyScalarTransferReview {...props} label="腰长" supportDescription="本目标必须已有四个腰部标记、腰长专属支持和审核；不会借用上身长度审核。"/>;
}
