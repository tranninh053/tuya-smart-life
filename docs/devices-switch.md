# Thiết bị công tắc, DPS và cảm biến

Tuya mô tả nút/gang qua DPS metadata:

- `dataPointInfo.dps`: giá trị hiện tại của từng DP.
- `dataPointInfo.dpName`: nhãn DP nếu Tuya trả về.
- `dp_schema`: schema có `code`, `type`, `mode`, `property`.

Integration expose DPS boolean giống switch/gang điều khiển được. Các trường phụ như indicator, backlight, countdown, fault hoặc setting sẽ bị bỏ qua khi nhận diện được.

Nếu thiết bị là quạt, DP nguồn được expose là `fan` thay vì `switch`.

Hẹn tắt và xóa timer thiết bị được mô tả riêng tại [Lịch và hẹn tắt thiết bị](devices-schedule.md).

## Cảm biến phổ biến

- `mcs`: cảm biến cửa. `doorcontact_state` được đảo để HA là `on` khi cửa mở.
- `hps`: cảm biến hiện diện.
- PIR/motion: binary sensor chuyển động.
- `wxkg`: text sensor hành động, ví dụ `1_press`, `1_double`, `1_long`.
- Điện/năng lượng: map voltage/current/power/energy theo schema nếu Tuya trả đủ.

## IP và trạng thái kết nối

- Chỉ hub hiển thị online/offline cloud.
- Thiết bị Wi-Fi/root có local IP sẽ có sensor `IP local`.
- Thiết bị con/remote ảo không hiển thị IP của hub như IP riêng.
- Mỗi thiết bị có cảm biến kết nối local/remote khi dữ liệu runtime đủ để xác định.
