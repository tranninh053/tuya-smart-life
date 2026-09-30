# Phát hiện API Android Tuya Smart

Tài liệu này tóm tắt kiến thức API rút ra từ Android package `com.tuya.smart` lấy từ Samsung S21 Ultra.

Workspace trích xuất:

- Package: `com.tuya.smart`
- APK đã pull:
  - `pulled/com.tuya.smart/base.apk`
  - `pulled/com.tuya.smart/split_config.arm64_v8a.apk`
- Decompile bằng:
  - `apktool` vào `decompiled/com.tuya.smart/`
  - `jadx` vào `jadx_out/com.tuya.smart/`

Quan sát quan trọng: app không expose REST path thông thường như `/v1/...` cho các luồng này. Nó dùng Tuya/Thing ATOP-style calls qua `ApiParams(apiName, version, countryCode?)`. SDK Tuya xử lý host routing, session, request signing và transport.

## Bản đồ API cần dùng

Tất cả call dưới đây là mobile ATOP call gửi dạng form data tới `POST /api.json`. Envelope quan trọng gồm `a`, `v`, `sid`, `gid`, `postData`, `time`, `requestId`, `chKey`, `et` và `sign`. Với `et=3`, `postData` và `result` được SDK mobile mã hóa.

### 1. Đăng nhập email/password

Chuỗi login account đã quan sát thành công:

| Bước | API name | Version | Session | Field `postData` chính | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| Token đăng nhập | `thing.m.user.username.token.get` | `2.0` | Không | `countryCode`, `username`, `isUid` | Gọi trước password login. `username` là email khi login email. |
| Đăng nhập bằng mật khẩu | `thing.m.user.email.password.login` | `3.0` | Không | `countryCode`, `email`, `passwd`, `token`, `ifencrypt`, `extInfo` | Đã xác nhận live với Smart Life profile. |
| Mobile password login | `thing.m.user.mobile.passwd.login` | `4.0` | Không | `countryCode`, `mobile`, `passwd`, `token`, `ifencrypt`, MFA metadata | Đã implement làm candidate; phone-account live verification còn pending. |

Static SDK wrappers cũng chứa tên `thing.m.*` cũ/nội bộ:

| Mục đích | API name | Version |
| --- | --- | --- |
| Token đăng nhập | `thing.m.user.username.token.get` | `2.0` |
| Email password login | `thing.m.user.email.password.login` | khả năng `2.0` |
| Mobile password login | `thing.m.user.mobile.passwd.login` | `4.0` |

### 2. Danh sách nhà

| Mục đích | API name | Version | Session | Field `postData` chính | Field response quan trọng |
| --- | --- | --- | --- | --- | --- |
| List homes/spaces | `m.life.home.space.list` | `1.0` | Có | none quan sát được | `homeId`/`gid`, `name`, `geoName`, `longitude`, `latitude`, role/admin fields |
| Home detail | `m.life.location.get` | `3.4` | Có | `gid` | `HomeResponseBean` chi tiết cho một nhà |

Capture live account tải nhà `Kiara` với `gid=92258848`.

### 3. Danh sách thiết bị và topology hub/child

App thường refresh thiết bị trong nhà qua batch call:

| Mục đích | API name | Version | Session | Field `postData` chính |
| --- | --- | --- | --- | --- |
| Batch wrapper | `smartlife.m.api.batch.invoke` hoặc `thing.m.api.batch.invoke` | `1.0` | Có | `gid`, `apis` |

Nested APIs hữu ích trong batch:

| Mục đích | API name | Version | Field chính |
| --- | --- | --- | --- |
| Thiết bị trong nhà | `m.life.my.group.device.list` | `2.2` | `gid` |
| Device groups | `m.life.my.group.device.group.list` | `4.3` | `gid` |
| Device relation list | `m.life.my.group.device.relation.list` | `3.2` | `gid` |
| Mesh list | `m.life.my.group.mesh.list` | `3.1` | `gid` |
| Sort/order list | `m.life.my.group.device.sort.list` | `2.1` | `gid` |
| Device reference info | `m.life.device.ref.info.my.list` | `7.2` | `gid`, `zigbeeGroup=true` |
| Shared devices | `thing.m.my.shared.device.list` | `3.2` | current user/session |
| Shared groups | `thing.m.my.shared.device.group.list` | khả năng `2.0` | current user/session |

Direct calls cho detail/subdevice:

| Mục đích | API name | Version | Field `postData` chính | Return model |
| --- | --- | --- | --- | --- |
| Device detail | `thing.m.device.get` | `4.1` | `devId`, tùy chọn `gid` | `DeviceRespBean` |
| Hub subdevice list | `thing.m.device.sub.list` | `2.1` | `meshId` | `ArrayList<DeviceRespBean>` |
| One subdevice detail | `thing.m.device.sub.get` | `2.1` | `meshId`, `devId` | `DeviceRespBean` |
| Local/direct device list | `m.life.app.smart.local.device.list` | `1.1` | `homeId`, `groupType=homeGroup` | `ThingLocalDeviceListDataBean.deviceList` |

Field cần giữ từ `DeviceRespBean`:

| Field | Ý nghĩa |
| --- | --- |
| `devId` | Tuya device id |
| `name` | Tên hiển thị |
| `productId`, `productVer`, `productInfo.category`, `productInfo.categoryCode` | Metadata sản phẩm/category |
| `uuid`, `mac`, `ip` | Định danh phần cứng/mạng khi có |
| `localKey`, `devKey`, `secKey` | Credential local protocol khi API trả về |
| `deviceTopo.meshId` | Ngữ cảnh mesh/gateway |
| `deviceTopo.nodeId` | Node id của subdevice |
| `deviceTopo.parentDevId` | Device id của parent gateway/hub |
| `communication.communicationModes` | Transport modes, hữu ích để phân loại Zigbee/BLE/Wi-Fi |
| `communication.connectionStatus` | Trạng thái kết nối |
| `meta` | Cờ phụ như Matter bridge gateway/subdevice |

Suy luận topology theo model app:

1. Build map `devId -> DeviceRespBean` từ home device list.
2. Thiết bị là child/subdevice nếu `deviceTopo.parentDevId` không rỗng; parent hub là `parentDevId`.
3. Nếu `parentDevId` rỗng nhưng `deviceTopo.meshId` có giá trị, xem `meshId` là ngữ cảnh mesh/gateway. Resolve tới hub bằng device có `devId` đó hoặc gọi `thing.m.device.sub.list`.
4. Hub/gateway là thiết bị được thiết bị khác tham chiếu bằng `parentDevId`, thiết bị có subdevice list hoặc Matter bridge gateway được chỉ ra trong `meta`.
5. Matter bridge child có thể được flag bằng `meta` chứa `matterBridgeSub`.

### 4. Local key, IP và BLE address

| Dữ liệu cần | Nguồn ưu tiên | Ghi chú fallback |
| --- | --- | --- |
| Local key | `thing.m.device.key.get` v1.0 | `DeviceRespBean.localKey` có thể đã có trong list/detail/local list. |
| IP address | `DeviceRespBean.ip` | Trả về trong list/detail/local direct-device APIs khi biết. |
| BLE address | `BLEScanDevBean.address` hoặc `ScanDeviceBean.address` | Cloud record thường có `mac` và `uuid`, không có field `bleAddress` riêng. Ưu tiên `mac`, rồi `uuid`, trừ khi có local BLE scan result. |

Local-key API:

| Mục đích | API name | Version | Field `postData` chính | Return model |
| --- | --- | --- | --- | --- |
| Lấy local keys | `thing.m.device.key.get` | `1.0` | `gwId`, tùy chọn `nodeIds` JSON string | `ArrayList<LocalKeyBean>` với `devId`, `localKey` |

Pattern call:

```json
{
  "gwId": "<devId>"
}
```

```json
{
  "gwId": "<hubDevId>",
  "nodeIds": "[\"<childNodeId>\"]"
}
```

Với subdevice, dùng `deviceTopo.parentDevId` làm `gwId` và `deviceTopo.nodeId` trong `nodeIds`. Nếu thiết bị kiểu mesh không có `parentDevId`, dùng mesh/hub id đã resolve từ `deviceTopo.meshId`.

## Đăng nhập

File bằng chứng:

- `jadx_out/com.tuya.smart/sources/com/thingclips/smart/login/skt/business/LoginBusiness.java`
- `jadx_out/com.tuya.smart/sources/com/thingclips/sdk/user/pqdbppq.java`

### Username token

- API name: `thing.m.user.username.token.get`
- Version: `2.0`
- Cần session: không
- Tham số chính: `countryCode`, `username`, `isUid`
- Bằng chứng: `LoginBusiness.java:59-65`

Đây là bước đầu trước password login. Token trả về được gửi cùng request password-login sau đó.

### Mobile password login

- API name: `thing.m.user.mobile.passwd.login`
- Version: `4.0`
- Cần session: không
- Tham số chính: `countryCode`, `mobile`, `passwd`, `token`, `ifencrypt`, `extInfo` chứa metadata MFA như `group` và `mfaCode`
- Bằng chứng: `LoginBusiness.java:129-138`

### Email password login

- API name: `thing.m.user.email.password.login`
- Version: khả năng `2.0` trong build này, được tham chiếu qua `GwBroadcastMonitorService.mVersion`
- Cần session: không
- Tham số chính: `countryCode`, `email`, `passwd`, `token`, `ifencrypt`, `extInfo`
- Bằng chứng: `LoginBusiness.java:141-150`

### API user liên quan

| Mục đích | API name | Version | Ghi chú |
| --- | --- | --- | --- |
| User info | `thing.m.user.info.get` | `1.0` | Cần session. Bằng chứng: `pqdbppq.java:339-342` |
| Logout | `thing.m.user.loginout` | unknown | Constant: `pqdbppq.java:66` |
| UID password login | `thing.m.user.uid.password.login` | unknown | Constant: `pqdbppq.java:45` |
| Email code login | `thing.m.user.email.code.login` | unknown | Constant: `pqdbppq.java:44` |
| Mobile code login | `thing.m.user.mobile.code.login` | unknown | Constant: `pqdbppq.java:107` |
| Domain query | `thing.m.app.domain.query` | unknown | Constant: `pqdbppq.java:48` |

## Home list và thiết bị

Các file `o00O0O.java`, `o0OOO0o.java` và plugin `TUNIHomeDataManager.json` cho thấy SDK gọi các API home/device nêu trên qua ATOP. Khi mapping sang integration, giữ nguyên `gid/homeId`, `devId`, `parentDevId`, `nodeId`, `localKey`, `ip`, `mac`, `uuid`, category và schema/DPS.

`dataPointInfo` rất quan trọng cho UI Home Assistant:

- `dps` cho giá trị hiện tại
- `dpName` cho nhãn nếu có
- schema code/property cho tên ổn định và scale của sensor

## IR APIs

Remote IR sử dụng cả infrared APIs và linkage/scene APIs:

| Mục đích | API name | Version/ghi chú |
| --- | --- | --- |
| Lấy gateway/remote IR | `tuya.m.infrared.gateway.get` | API app panel |
| Lấy keydata IR | `tuya.m.infrared.keydata.get` | Trả compress pulse/head/type/delay |
| Action devices | `thing.m.linkage.dev.list` | `3.0`/`4.0`, `sourceType=action` |
| Action functions | `thing.m.linkage.function.list` | `3.0` |
| Scene rule list | `thing.m.linkage.rule.query`, `thing.m.linkage.rule.simple.query` | `5.0`/`4.0` |
| Scene rule detail | `thing.m.linkage.rule.detail.find` | `2.0` |

DP `201` là đường gửi IR keydata local. Payload dạng:

```json
{
  "control": "send_ir",
  "head": "...",
  "key1": "001%^...",
  "type": 0,
  "delay": 300
}
```

Lệnh phải gửi tới hub IR vật lý bằng local key/IP/protocol của hub. Remote ảo chỉ dùng cho identity/name/report metadata.

## MQTT mobile

Android SDK set MQTT config từ user object sau login:

```java
mqttConnectConfig.setUid(iBaseUser.getUid());
mqttConnectConfig.setEcode(iBaseUser.getEcode());
mqttConnectConfig.setPartnerIdentity(iBaseUser.getPartnerIdentity());
mqttConnectConfig.setToken(iBaseUser.getSid());
```

Integration dùng `sid` làm username, `md5_hex(ecode)[8:24]` làm password, `uid` làm uid và build client id deterministic từ package/device id/uid. Broker lấy từ domain login nếu có, fallback `mqtts://m1.tuyaus.com:8883`.

## Signing và crypto

Các helper trong `tools/` giữ nguyên để kiểm chứng:

- `tools/tuya_mobile_crypto.js`: canonical sign input, swapped MD5, decrypt response `et=3` khi có AES key.
- `tools/tuya_mobile_crypto.py`: extract BMP key và derive native signing key.
- `tools/frida_tuya_network_crypto_dump.js`: hook Android app để log sign input/result và crypto plaintext.
- `tools/frida_tuya_sign_key_probe.js`: xác minh native signing algorithm trong process.

Không commit APK, source decompile, capture raw, token, `sid`, `ecode`, local key hoặc thông tin tài khoản thật.

## Ghi chú cập nhật

Khi cập nhật app version mới, cần xác minh lại ít nhất các phần sau trước khi đổi default trong integration:

1. Endpoint ATOP và region/domain sau login.
2. Request signing/canonical input.
3. Token đăng nhập và password login `et=0`.
4. Home list và device list có `localKey`, topology, DPS/schema.
5. IR keydata/action APIs còn trả DP `201` hợp lệ.
6. MQTT credential derivation từ `sid`/`ecode`/`uid` còn đúng.
