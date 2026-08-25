# -*- coding: utf-8 -*-
"""Core translation data (modules/pricing/common/finalCta) for ko, vi."""

MODULES_HEADER = {
    "ko": {"kicker": "Avenqo 모듈", "title": "필요에 따라 확장되는 단일 모듈형 플랫폼",
           "subtitle": "오늘 필요한 모듈을 활성화하고, 나중에 도구를 바꾸지 않고도 확장하세요.",
           "discover": "더 알아보기", "availableNow": "지금 이용 가능", "comingSoon": "출시 예정"},
    "vi": {"kicker": "Mô-đun Avenqo", "title": "Một nền tảng mô-đun phát triển theo nhu cầu của bạn",
           "subtitle": "Kích hoạt các mô-đun bạn cần hôm nay và mở rộng sau này mà không cần thay đổi công cụ.",
           "discover": "Tìm hiểu thêm", "availableNow": "Hiện có sẵn", "comingSoon": "Sắp ra mắt"},
}

MODULE_NAMES = ["Retail Intelligence", "CRM AI", "OCR AI", "Voice AI", "Media AI", "Accounting AI", "Legal AI"]

MODULE_DESCRIPTIONS = {
    "ko": ["소매업을 위한 실시간 판매 및 재고 분석.", "더 스마트한 영업 파이프라인을 위한 AI 기반 고객 관계 관리.",
           "송장 및 스캔한 문서에서 자동 데이터 추출.", "고객 통화를 기록하고 추적하는 음성 비서.",
           "시각 및 마케팅 콘텐츠 제작 및 분석.", "회계 및 재무 조정 자동화.", "AI의 도움으로 계약서 검토 및 요약."],
    "vi": ["Phân tích doanh số và hàng tồn kho theo thời gian thực cho ngành bán lẻ.", "Quản lý quan hệ khách hàng được hỗ trợ bởi AI cho quy trình bán hàng thông minh hơn.",
           "Trích xuất dữ liệu tự động từ hóa đơn và tài liệu đã quét.", "Trợ lý giọng nói để phiên âm và theo dõi các cuộc gọi của khách hàng.",
           "Tạo và phân tích nội dung hình ảnh và tiếp thị.", "Tự động hóa kế toán và đối chiếu tài chính.", "Xem xét và tóm tắt hợp đồng với sự trợ giúp của AI."],
}

PRICING = {
    "ko": {
        "kicker": "가격", "title": "성장의 모든 단계를 위한 플랜", "subtitle": "데모로 시작한 다음 회사 규모에 맞는 플랜을 선택하세요.",
        "popular": "가장 인기 있음", "priceLabel": "문의 시 가격 안내",
        "plans": [
            {"tier": "Demo", "title": "귀사의 데이터로 Avenqo를 체험해보세요", "priceLabel": "무료", "items": ["기간 제한 액세스", "데모 또는 자체 데이터", "이메일 지원"], "action": "데모 요청"},
            {"tier": "Professional", "title": "성장을 원하는 기업을 위한 플랜", "priceLabel": "문의 시 가격 안내", "items": ["모든 핵심 모듈", "확장 가능한 사용자 수", "우선 지원"], "action": "문의하기"},
            {"tier": "Enterprise", "title": "고급 요구사항이 있는 조직을 위한 플랜", "priceLabel": "문의 시 가격 안내", "items": ["맞춤형 통합", "전담 계정 관리자", "서비스 수준 계약"], "action": "영업팀에 문의"},
        ],
    },
    "vi": {
        "kicker": "Bảng giá", "title": "Một gói cho mỗi giai đoạn phát triển của bạn", "subtitle": "Bắt đầu với bản demo, sau đó chọn gói phù hợp với quy mô công ty của bạn.",
        "popular": "Phổ biến nhất", "priceLabel": "Giá theo yêu cầu",
        "plans": [
            {"tier": "Demo", "title": "Dùng thử Avenqo với dữ liệu của bạn", "priceLabel": "Miễn phí", "items": ["Truy cập giới hạn thời gian", "Dữ liệu demo hoặc dữ liệu riêng", "Hỗ trợ qua email"], "action": "Yêu cầu demo"},
            {"tier": "Professional", "title": "Dành cho các công ty muốn phát triển", "priceLabel": "Giá theo yêu cầu", "items": ["Tất cả các mô-đun cốt lõi", "Số lượng người dùng có thể mở rộng", "Hỗ trợ ưu tiên"], "action": "Liên hệ với chúng tôi"},
            {"tier": "Enterprise", "title": "Dành cho tổ chức có nhu cầu nâng cao", "priceLabel": "Giá theo yêu cầu", "items": ["Tích hợp tùy chỉnh", "Quản lý tài khoản chuyên trách", "Thỏa thuận cấp độ dịch vụ"], "action": "Liên hệ bộ phận bán hàng"},
        ],
    },
}

COMMON_OVERRIDES = {
    "ko": {"tryFree": "Avenqo 체험하기", "noCreditCard": "맞춤형 설정"},
    "vi": {"tryFree": "Dùng thử Avenqo", "noCreditCard": "Thiết lập cá nhân hóa"},
}

FINALCTA_TRYFREE = {code: v["tryFree"] for code, v in COMMON_OVERRIDES.items()}
