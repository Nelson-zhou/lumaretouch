import {BodyScalarTransferReview,type BodyScalarReviewProps} from '../bodyScalar/BodyScalarTransferReview';
export function TorsoTransferReview(props:BodyScalarReviewProps){
  return <BodyScalarTransferReview {...props} label="上身长度" supportDescription=""/>;
}
