# -*- coding: utf-8 -*-
"""Full assistant + auth sections for ko, vi (these locales lacked the sections entirely)."""

ASSISTANT = {
    "ko": {
        "title": "비즈니스에 대해 Avenqo에게 물어보세요", "subtitle": "비즈니스 질문을 하면 Avenqo가 회사에서 사용 가능한 정보를 활용합니다.",
        "connectData": "비즈니스 데이터 연결", "newConversation": "새 대화",
        "conversationsEmpty": "대화가 여기에 표시됩니다.", "deleteConversation": "대화 삭제",
        "thinking": "Avenqo가 생각 중입니다...", "retry": "다시 시도",
        "sourcesLabel": "출처", "newest": "최신순", "you": "나", "avenqoAi": "Avenqo AI",
        "suggestions": ["제 매출 실적은 어떤가요?", "어떤 고객에게 관심이 필요한가요?", "이번 달에 무엇이 바뀌었나요?", "제 비즈니스 실적을 요약해주세요."],
    },
    "vi": {
        "title": "Hỏi Avenqo về doanh nghiệp của bạn", "subtitle": "Đặt câu hỏi kinh doanh và Avenqo sẽ sử dụng thông tin có sẵn cho công ty của bạn.",
        "connectData": "Kết nối dữ liệu doanh nghiệp của bạn", "newConversation": "Cuộc trò chuyện mới",
        "conversationsEmpty": "Các cuộc trò chuyện của bạn sẽ xuất hiện ở đây.", "deleteConversation": "Xóa cuộc trò chuyện",
        "thinking": "Avenqo đang suy nghĩ...", "retry": "Thử lại",
        "sourcesLabel": "Nguồn", "newest": "Mới nhất", "you": "Bạn", "avenqoAi": "Avenqo AI",
        "suggestions": ["Doanh số của tôi đang hoạt động như thế nào?", "Khách hàng nào cần được chú ý?", "Điều gì đã thay đổi trong tháng này?", "Tóm tắt hiệu suất kinh doanh của tôi."],
    },
}

AUTH = {
    "ko": {
        "tagline": "비즈니스 의사결정을 위한 AI 플랫폼", "loginTitle": "로그인", "loginSubtitle": "Avenqo 작업 공간에 액세스하세요.",
        "registerTitle": "조직 만들기", "registerSubtitle": "몇 분 만에 Avenqo 작업 공간을 설정하세요.",
        "forgotTitle": "비밀번호 찾기", "forgotSubtitle": "비밀번호를 재설정할 링크를 받으세요.",
        "verifyTitle": "이메일 인증", "verifySubtitle": "이메일로 받은 토큰을 입력하세요.",
        "resetTitle": "새 비밀번호", "resetSubtitle": "새롭고 안전한 비밀번호를 선택하세요.",
        "organisation": "조직", "billingEmail": "청구 이메일", "firstName": "이름", "lastName": "성",
        "email": "이메일", "password": "비밀번호", "emailToken": "이메일로 받은 토큰",
        "requiredField": "필수 항목", "forgotPassword": "비밀번호 찾기", "createOrganisation": "조직 만들기",
        "backToLogin": "로그인으로 돌아가기", "home": "홈",
        "registerSuccess": "계정이 생성되었습니다. 이메일 주소를 확인하세요.",
        "forgotSuccess": "계정이 존재하면 이메일이 발송되었습니다.",
        "verifySuccess": "이메일이 인증되었습니다. 이제 로그인할 수 있습니다.",
        "resetSuccess": "비밀번호가 변경되었습니다. 이제 로그인할 수 있습니다.",
        "genericError": "서비스가 일시적으로 사용할 수 없습니다.",
    },
    "vi": {
        "tagline": "Nền tảng AI cho các quyết định kinh doanh của bạn", "loginTitle": "Đăng nhập", "loginSubtitle": "Truy cập không gian làm việc Avenqo của bạn.",
        "registerTitle": "Tạo tổ chức", "registerSubtitle": "Thiết lập không gian làm việc Avenqo của bạn trong vài phút.",
        "forgotTitle": "Quên mật khẩu", "forgotSubtitle": "Nhận liên kết để đặt lại mật khẩu của bạn.",
        "verifyTitle": "Xác minh email của bạn", "verifySubtitle": "Nhập mã bạn đã nhận được qua email.",
        "resetTitle": "Mật khẩu mới", "resetSubtitle": "Chọn một mật khẩu mới, an toàn.",
        "organisation": "Tổ chức", "billingEmail": "Email thanh toán", "firstName": "Tên", "lastName": "Họ",
        "email": "Email", "password": "Mật khẩu", "emailToken": "Mã nhận được qua email",
        "requiredField": "Trường bắt buộc", "forgotPassword": "Quên mật khẩu", "createOrganisation": "Tạo tổ chức",
        "backToLogin": "Quay lại đăng nhập", "home": "Trang chủ",
        "registerSuccess": "Đã tạo tài khoản. Kiểm tra địa chỉ email của bạn.",
        "forgotSuccess": "Nếu tài khoản tồn tại, một email đã được gửi.",
        "verifySuccess": "Email đã được xác minh. Bạn có thể đăng nhập ngay bây giờ.",
        "resetSuccess": "Mật khẩu đã được thay đổi. Bạn có thể đăng nhập ngay bây giờ.",
        "genericError": "Dịch vụ tạm thời không khả dụng.",
    },
}
