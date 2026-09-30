# Ghi chú reverse engineering và MITM

Tài liệu này tách riêng các ghi chú reverse engineering, MITM, replay, signing và crypto khỏi hướng dẫn cài đặt Home Assistant dành cho người dùng.

Bản đồ API đầy đủ và bằng chứng Android nằm ở:

- [Phát hiện API Android Tuya Smart](tuya-smart-android-api-findings.md)

## Phạm vi

Integration Home Assistant trong repository này đã bundle mobile signing profile cần thiết cho người dùng bình thường. Bạn không cần nội dung trong tài liệu này để cài hoặc dùng integration.

Những ghi chú này hữu ích khi cần:

- replay request mobile API đã capture
- kiểm tra capture MITM
- test login mobile API mới ngoài app
- xác minh request signing
- điều tra request/response mã hóa `et=3`
- cập nhật integration cho phiên bản app Tuya/Smart Life mới

Không commit APK, source decompile, credential tài khoản, session token hoặc raw local key.

## Phát hiện API chính

Android app dùng các call kiểu Tuya/Thing ATOP qua `POST /api.json` thay vì REST path thông thường. Envelope quan trọng gồm `a`, `v`, `sid`, `postData`, `time`, `requestId`, `clientId`, `deviceId`, `chKey`, `et` và `sign`.

Các call plaintext `et=0` đã xác nhận và được integration dùng:

| Mục đích | API | Version | Payload chính |
| --- | --- | --- | --- |
| Token đăng nhập | `thing.m.user.username.token.get` | `2.0` | `countryCode`, `username`, `isUid` |
| Đăng nhập email/password | `thing.m.user.email.password.login` | `3.0` | `countryCode`, `email`, `passwd`, `token`, `ifencrypt` |
| Đăng nhập mobile/password | `thing.m.user.mobile.passwd.login` hoặc fallback `smartlife.m.user.mobile.passwd.login` | `4.0` | `countryCode`, `mobile`, `passwd`, `token`, `ifencrypt`, metadata MFA |
| Danh sách nhà | `m.life.home.space.list` | `1.0` | none |
| Thiết bị trong nhà | `m.life.my.group.device.list` | `2.2` | `gid` |
| Chi tiết thiết bị | `thing.m.device.get` | `4.1` | `devId` |
| Quan hệ/thứ tự thiết bị | `m.life.my.group.device.relation.list` | `3.2` | `gid` |
| Danh sách compact/energy | `m.energy.home.device.list` | `3.0` | `groupId`, tùy chọn `type` |
| Danh sách thiết bị local/direct | `m.life.app.smart.local.device.list` | `1.1` | `homeId`, `groupType=homeGroup` |
| Danh sách device cho scene/action | `thing.m.linkage.dev.list` | `3.0`/`4.0` | `gid`, `sourceType=action` |
| Danh sách function cho scene/action | `thing.m.linkage.function.list` | `3.0` | `params.gid`, `params.devId` |
| Danh sách scene rule | `thing.m.linkage.rule.query` / `thing.m.linkage.rule.simple.query` | `5.0` / `4.0` | top-level `gid` |
| Chi tiết scene rule | `thing.m.linkage.rule.detail.find` | `2.0` | top-level `gid`, `ruleId` |

Một số batch/plugin API sau login vẫn yêu cầu SDK encryption với `et=3`.

## Nguồn DPS cho switch button

Với switch/gang device, nút điều khiển lấy từ DPS metadata trong mobile API:

- `dataPointInfo.dps`: giá trị DP hiện tại
- `dataPointInfo.dpName`: nhãn DP nếu có
- `dataPointInfo.dpsTime`: timestamp cập nhật cuối

Kiểm tra live cho thấy:

- `m.life.my.group.device.list` v2.2 trả `dataPointInfo.dps`.
- `thing.m.device.get` v4.1 trả cùng block `dataPointInfo`.
- `dataPointInfo.dpName` có thể rỗng toàn bộ, nên integration phải fallback về DP id hoặc schema code.
- `m.energy.home.device.list` v3.0 trả danh sách compact không có nhãn DPS.
- `m.life.app.smart.local.device.list` v1.1 có thể trả object rỗng dù list thiết bị thường vẫn hoạt động.

Integration expose DPS boolean giống switch button/gang và bỏ qua các field phụ như indicator/backlight/countdown khi nhận diện được.

## Phát hiện điều khiển IR remote

Thiết bị IR Tuya gồm hub IR thật và remote ảo. App mobile không điều khiển remote ảo bằng local child-device DPS thông thường. Thay vào đó, scene/action layer build IR action rồi publish raw DPS tới hub.

Bằng chứng Android:

- `ActionConstantKt.ACTION_TYPE_IRISSUEVII` là `irIssueVii`.
- `ExecuteSceneExtensionsKt` chạy `irIssueVii` bằng cách lấy `SceneAction.executorProperty` làm `actionDps` và `SceneAction.extraProperty` làm `reportDps`.
- `DeviceUtil.infraredPublishDps(infraGwId, subDeviceId, actionDps, reportDps)` gọi `newDeviceInstance(infraGwId).infraredPublishDps(...)`.
- `AbsThingDevice.infraredPublishDps(subDevId, actionDps, reportDps)` parse JSON `actionDps` và gửi nó như local control DPS qua hub. `subDevId` chỉ định remote IR ảo; `reportDps` chỉ dùng để app tự report state sau publish thành công. Frame action gửi tới hub thật và không đóng gói remote ảo thành local `cid`/child target.

Đường integration dùng:

```text
mobile action API -> actionDps/reportDps -> Home Assistant -> IR hub IP/local key -> Tuya local protocol
```

API discovery dùng:

- `thing.m.linkage.dev.list` v3.0/v4.0 với `{"gid": home_id, "sourceType": "action"}` để lấy action/remote id, tên và metadata extension.
- `thing.m.linkage.function.list` v3.0 với `{"params": {"gid": home_id, "devId": remote_id}}` để lấy function và datapoint.
- `thing.m.linkage.rule.query`, `thing.m.linkage.rule.simple.query`, `thing.m.linkage.rule.detail.find` để đọc `SceneAction` đã lưu. IR scene action dùng `actionExecutor=irIssueVii`, `executorProperty` là `actionDps`, `extraProperty` là `reportDps`.

Với remote thường, mỗi action DPS hợp lệ thành một button Home Assistant. Với AC/climate, integration phân loại remote theo category/name/function metadata rồi map `power`, `mode`, `temp`, `wind` thành climate entity. State IR climate là optimistic vì điều hòa vật lý không report state qua IR.

## Tool replay capture

`tools/replay_tuya_capture_request.py` replay request Tuya mobile đã ký từ capture mitmproxy local:

```bash
python3 tools/replay_tuya_capture_request.py /path/to/capture.mitm --list
python3 tools/replay_tuya_capture_request.py /path/to/capture.mitm --api m.life.home.space.list
python3 tools/replay_tuya_capture_request.py /path/to/capture.mitm --api m.life.app.smart.local.device.list
```

Tool này dùng lại envelope đã ký, session fields và `postData` đã mã hóa trong capture. Nó không tự tạo chữ ký mới và không tự decrypt encrypted `result` payload.

## Tool login standalone

`tools/tuya_mobile_login.py` thực hiện login email/password hoặc mobile/password mới bằng mobile request signature đã khôi phục. Giữ credential và app material trong biến môi trường:

```bash
export TUYA_USERNAME='user@example.com'
# hoặc: export TUYA_USERNAME='0912345678'
export TUYA_PASSWORD='...'
export TUYA_APP_ID='<client-id>'
export TUYA_APP_SECRET='<app-secret>'
export TUYA_CERT_SHA256='<apk-cert-sha256>'
export TUYA_BMP='/path/to/t_s.bmp'

python3 tools/tuya_mobile_login.py
python3 tools/tuya_mobile_login.py --username 0912345678
python3 tools/tuya_mobile_login.py --action homes
python3 tools/tuya_mobile_login.py --action devices --home-id <home-id>
python3 tools/tuya_mobile_login.py --action ir --home-id <home-id>
python3 tools/tuya_mobile_login.py --action devices --json
```

Script mặc định redact secret session. Output thiết bị gồm phân loại hub/child, parent id, trạng thái có local key, IP, MAC, UUID, product id và online state. Output IR gồm remote id, category suy ra, hub id, action functions và payload `actionDps` đã parse. Chỉ dùng `--show-secrets` khi cố ý cần raw `sid`, `ecode`, token, local key hoặc full raw API payload.

## Helper crypto mobile

`tools/tuya_mobile_crypto.js` implement format input signing phía Java, swapped MD5 cho `postData` mã hóa và decrypt response `et=3` khi biết AES key theo request:

```bash
node tools/tuya_mobile_crypto.js post-md5 '{"homeId":92258848}'
node tools/tuya_mobile_crypto.js sign-input '{"a":"m.life.home.space.list","v":"1.0"}'
node tools/tuya_mobile_crypto.js request-sign --native-key-hex <key> --input '<canonical-input>'
node tools/tuya_mobile_crypto.js decrypt-response --key-hex <key> --response '<json>'
```

`tools/tuya_mobile_crypto.py` có helper suy ra native signing key:

```bash
python3 tools/tuya_mobile_crypto.py extract-bmp-key --app-id <client-id> --bmp /path/to/t_s.bmp
python3 tools/tuya_mobile_crypto.py derive-native-key \
  --package-name <android-package> \
  --cert-sha256 <apk-cert-sha256> \
  --app-id <client-id> \
  --app-secret <app-secret> \
  --bmp /path/to/t_s.bmp
```

## Helper Frida

`tools/frida_tuya_network_crypto_dump.js` hook Android app để log native sign input/result, key mã hóa theo request, plaintext request mã hóa và plaintext response đã decrypt.

`tools/frida_tuya_sign_key_probe.js` xác minh thuật toán request-signing native trong process. Nó kiểm tra command `1` tương đương HMAC-SHA256 với native key đã init và mặc định không in key bytes.

## Cập nhật cho app version mới

Khi Tuya/Smart Life đổi signing material:

1. Pull APK/splits từ thiết bị thật.
2. Patch anti-tamper/certificate pinning chỉ trong môi trường test local.
3. Capture login và device-list calls bằng mitmproxy.
4. Xác minh native signing key và canonicalization bằng Frida.
5. Confirm login, home list và device list bằng standalone scripts.
6. Chỉ cập nhật defaults của integration sau khi plaintext `et=0` login và metadata thiết bị đã được xác nhận.

Giữ raw captures và app binaries ngoài repository.
