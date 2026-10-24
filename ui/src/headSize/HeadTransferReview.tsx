import {BodyScalarTransferReview,type BodyScalarReviewProps} from '../bodyScalar/BodyScalarTransferReview';
export function HeadTransferReview(props:BodyScalarReviewProps){
  return <BodyScalarTransferReview {...props} kind="head" label="小头" supportDescription="本目标必须已有当前完整头发/头部框、明确缩小中心、外围过渡框、实测姿态和本人面部归属的独立审核。不会复制源图几何、蒙版或支持，也不会借用脸部大小、上身长度或腰长审核。"/>;
}
