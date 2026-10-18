/* libraw_layout.c —— 用真头文件把 ctypes 绑定需要的字段偏移/长度/常量**打印**出来。
 *
 * 为什么要有这一份（而不是在 Python 里手写偏移）：本仓的纪律是"常量必须有出处"。
 * libraw_data_t 是 C 结构，字段位置随 LibRaw 版本变；手写偏移表一旦与 .so 不一致，
 * 表现是读到一堆看起来像数据的垃圾（尺寸读成 0、make 读成随机字节），而不是报错。
 * 这里让编译器按**装机那一刻的真头**算 offsetof/sizeof，产出可核对的 JSON，再由
 * gen-libraw-layout.sh 写成 ops/libraw_layout.py，并在 Python 侧留一份来源指纹
 * （头文件 sha256 + LibRaw 版本 + 编译器版本）。运行期还有一道真值自检兜底。
 *
 * 只在开发机跑；不进发布物（发布物里带的是它生成的 .py）。
 */
#include <stdio.h>
#include <stddef.h>
#include <time.h>
#include <libraw.h>

#define OFF(struct_, field_) printf("  \"%s.%s\": %zu,\n", #struct_, #field_, offsetof(struct_, field_))
#define SZ(struct_)          printf("  \"sizeof." #struct_ "\": %zu,\n", sizeof(struct_))
#define CONST(name_)         printf("  \"" #name_ "\": %d,\n", (int)(name_))

int main(void)
{
    printf("{\n");

    /* --- 顶层：libraw_data_t（C API 的 handle 就指向它）--- */
    SZ(libraw_data_t);
    OFF(libraw_data_t, sizes);
    OFF(libraw_data_t, idata);
    OFF(libraw_data_t, other);
    OFF(libraw_data_t, thumbnail);
    OFF(libraw_data_t, params);
    OFF(libraw_data_t, color);

    /* --- sizes：满幅尺寸与方向（导出要的是这个，不是代理档）--- */
    SZ(libraw_image_sizes_t);
    OFF(libraw_image_sizes_t, raw_height);
    OFF(libraw_image_sizes_t, raw_width);
    OFF(libraw_image_sizes_t, height);
    OFF(libraw_image_sizes_t, width);
    OFF(libraw_image_sizes_t, top_margin);
    OFF(libraw_image_sizes_t, left_margin);
    OFF(libraw_image_sizes_t, iheight);
    OFF(libraw_image_sizes_t, iwidth);
    OFF(libraw_image_sizes_t, flip);

    /* --- idata：厂商/机型/色彩描述/DNG 版本（能力上报与 Exif 面板用）--- */
    SZ(libraw_iparams_t);
    OFF(libraw_iparams_t, make);
    OFF(libraw_iparams_t, model);
    OFF(libraw_iparams_t, software);
    OFF(libraw_iparams_t, normalized_make);
    OFF(libraw_iparams_t, normalized_model);
    OFF(libraw_iparams_t, dng_version);
    OFF(libraw_iparams_t, is_foveon);
    OFF(libraw_iparams_t, colors);
    OFF(libraw_iparams_t, filters);
    OFF(libraw_iparams_t, cdesc);

    /* --- other：拍摄参数（Exif 面板：ISO / 快门 / 光圈 / 焦距）--- */
    SZ(libraw_imgother_t);
    OFF(libraw_imgother_t, iso_speed);
    OFF(libraw_imgother_t, shutter);
    OFF(libraw_imgother_t, aperture);
    OFF(libraw_imgother_t, focal_len);
    OFF(libraw_imgother_t, timestamp);

    /* --- thumbnail：浏览快通道（内嵌预览）--- */
    SZ(libraw_thumbnail_t);
    OFF(libraw_thumbnail_t, tformat);
    OFF(libraw_thumbnail_t, twidth);
    OFF(libraw_thumbnail_t, theight);
    OFF(libraw_thumbnail_t, tlength);
    OFF(libraw_thumbnail_t, tcolors);
    OFF(libraw_thumbnail_t, thumb);

    /* --- params：去马赛克与白平衡的开关（16-bit 母档那一臂）--- */
    SZ(libraw_output_params_t);
    OFF(libraw_output_params_t, use_camera_wb);
    OFF(libraw_output_params_t, use_auto_wb);
    OFF(libraw_output_params_t, use_camera_matrix);
    OFF(libraw_output_params_t, no_auto_bright);
    OFF(libraw_output_params_t, output_bps);
    OFF(libraw_output_params_t, output_color);
    OFF(libraw_output_params_t, output_tiff);
    OFF(libraw_output_params_t, user_flip);
    OFF(libraw_output_params_t, user_qual);
    OFF(libraw_output_params_t, user_black);
    OFF(libraw_output_params_t, highlight);
    OFF(libraw_output_params_t, half_size);
    OFF(libraw_output_params_t, four_color_rgb);
    OFF(libraw_output_params_t, no_interpolation);
    OFF(libraw_output_params_t, no_auto_scale);
    OFF(libraw_output_params_t, gamm);
    OFF(libraw_output_params_t, cropbox);
    OFF(libraw_output_params_t, bright);

    /* --- color：黑白电平与相机矩阵（原生线性那一档要照它做，不能猜）--- */
    SZ(libraw_colordata_t);
    OFF(libraw_colordata_t, black);
    OFF(libraw_colordata_t, white);
    OFF(libraw_colordata_t, cam_mul);
    OFF(libraw_colordata_t, rgb_cam);
    OFF(libraw_colordata_t, raw_bps);

    /* --- make_mem_image 的产物：16-bit RGB 矩阵就在这里 --- */
    SZ(libraw_processed_image_t);
    OFF(libraw_processed_image_t, type);
    OFF(libraw_processed_image_t, height);
    OFF(libraw_processed_image_t, width);
    OFF(libraw_processed_image_t, colors);
    OFF(libraw_processed_image_t, bits);
    OFF(libraw_processed_image_t, data_size);
    OFF(libraw_processed_image_t, data);

    /* --- 常量：枚举值逐个打印，Python 侧不许凭记忆写数字（名字全部从真头里核过）--- */
    CONST(LIBRAW_SUCCESS);
    CONST(LIBRAW_UNSPECIFIED_ERROR);
    CONST(LIBRAW_FILE_UNSUPPORTED);
    CONST(LIBRAW_REQUEST_FOR_NONEXISTENT_IMAGE);
    CONST(LIBRAW_OUT_OF_ORDER_CALL);
    CONST(LIBRAW_NO_THUMBNAIL);
    CONST(LIBRAW_UNSUPPORTED_THUMBNAIL);
    CONST(LIBRAW_INPUT_CLOSED);
    CONST(LIBRAW_NOT_IMPLEMENTED);
    CONST(LIBRAW_REQUEST_FOR_NONEXISTENT_THUMBNAIL);
    CONST(LIBRAW_UNSUFFICIENT_MEMORY);
    CONST(LIBRAW_DATA_ERROR);
    CONST(LIBRAW_IO_ERROR);
    CONST(LIBRAW_BAD_CROP);
    CONST(LIBRAW_TOO_BIG);
    CONST(LIBRAW_MEMPOOL_OVERFLOW);
    CONST(LIBRAW_THUMBNAIL_UNKNOWN);
    CONST(LIBRAW_THUMBNAIL_JPEG);
    CONST(LIBRAW_THUMBNAIL_BITMAP);
    CONST(LIBRAW_THUMBNAIL_BITMAP16);
    CONST(LIBRAW_THUMBNAIL_LAYER);
    CONST(LIBRAW_THUMBNAIL_ROLLEI);
    CONST(LIBRAW_THUMBNAIL_H265);
    CONST(LIBRAW_IMAGE_JPEG);
    CONST(LIBRAW_IMAGE_BITMAP);
    CONST(LIBRAW_COLORSPACE_NotFound);
    CONST(LIBRAW_COLORSPACE_sRGB);
    CONST(LIBRAW_COLORSPACE_AdobeRGB);
    CONST(LIBRAW_COLORSPACE_Uncalibrated);
    CONST(LIBRAW_COLORSPACE_CameraLinear);
    CONST(LIBRAW_COLORSPACE_Unknown);

    printf("  \"libraw_version\": \"%s\",\n", libraw_version());
    printf("  \"time_t_size\": %zu\n", sizeof(time_t));
    printf("}\n");
    return 0;
}
