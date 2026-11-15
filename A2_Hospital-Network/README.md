# Thiết kế và mô phỏng mạng cho bệnh viện quy mô lớn

## Tổng quan
Dự án thiết kế và mô phỏng hệ thống mạng cho một bệnh viện gồm trụ sở chính (TP. Hồ Chí Minh, 2 tòa A và B, 600 máy trạm, 10 server) và 2 cơ sở phụ (đường ĐBP và BHTQ, mỗi nơi 260 máy trạm, 2 server). Hệ thống được mô phỏng và kiểm thử bằng Cisco Packet Tracer.

## Bối cảnh bài toán
**Khách hàng:** CCC (Computer & Construction Consultant) Agency  
**Phạm vi:** Thiết kế mạng cho trụ sở chính (TP. Hồ Chí Minh) và hai cơ sở phụ (đường ĐBP và đường BHTQ).  

## Mục tiêu
- Thiết kế topology mạng cho trụ sở chính và các cơ sở phụ của bệnh viện.
- Cho phép các khoa/phòng ban và các tòa nhà giao tiếp với nhau.
- Đảm bảo khả năng mở rộng, tính sẵn sàng cao và bảo mật.
- Mô phỏng và kiểm thử mạng về hiệu năng và độ tin cậy.

## Công cụ và công nghệ
- **Phần mềm mô phỏng:** Cisco Packet Tracer hoặc GNS3.
- **Công nghệ mạng:** GPON, GigaEthernet, SD-WAN, MPLS.
- **Biện pháp bảo mật:** Firewall, IPS/IDS, VPN.
## Tóm tắt thiết kế
- **Kiến trúc:** trụ sở chính dùng mô hình 3 lớp (access, distribution, core); hai cơ sở phụ dùng collapsed core (2 lớp).
- **Phân vùng:** VLAN theo khoa/phòng ban, server farm, DMZ (email, DNS, web), VLAN quản lý và camera; cặp firewall bảo vệ ranh giới mạng.
- **Địa chỉ IP:** dải `10.0.0.0/8`, chia khối theo tòa/cơ sở (`10.1` tòa A, `10.2` tòa B, `10.3` ĐBP, `10.4` BHTQ, `10.5` khu hạ tầng trung tâm), tổng cộng 44 VLAN, mỗi subnet dự phòng 20% tăng trưởng.
- **Internet:** Dual DSL có cân bằng tải qua trụ sở chính, mỗi đường tối thiểu 500 Mbps xuống và 100 Mbps lên.
- **WAN:** kênh truyền riêng (leased line) 200 Mbps nối từng cơ sở phụ về trụ sở chính, định tuyến OSPF.
- **Tính sẵn sàng cao:** 2 edge router, 2 firewall, 2 core switch; khoa Cấp cứu và ICU đấu dự phòng vào 2 distribution switch của tòa B; server DR đặt tại BHTQ.