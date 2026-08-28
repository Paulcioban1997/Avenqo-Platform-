const publicPaths = <String>{
  '/',
  '/pricing',
  '/login',
  '/register',
  '/forgot-password',
  '/verify-email',
  '/reset-password',
};

const subscriptionExemptPaths = <String>{
  '/billing',
  '/pricing',
  '/onboarding',
  '/settings',
};

bool subscriptionAllowsTenantApp(String status) =>
  const {'active', 'trialing'}.contains(status.trim().toLowerCase());

String? subscriptionRedirect({
  required String path,
  required bool isAuthenticated,
  required bool isPlatformAdmin,
  required bool hasActiveSubscription,
  String? onboardingStatus,
}) {
  final isPublic = publicPaths.contains(path);
  final isAdminPath = path == '/admin' || path.startsWith('/admin/');

  if (!isAuthenticated) {
    return isPublic ? null : '/login';
  }
  if (isAdminPath && !isPlatformAdmin) {
    return hasActiveSubscription ? '/dashboard' : '/billing';
  }
  if (path == '/login') {
    if (isPlatformAdmin) return '/admin';
    return hasActiveSubscription ? '/dashboard' : '/billing';
  }
  if (isPlatformAdmin || isAdminPath || isPublic) {
    return null;
  }
  if (!hasActiveSubscription && !subscriptionExemptPaths.contains(path)) {
    return '/billing';
  }
  if (hasActiveSubscription &&
      onboardingStatus == 'pending' &&
      path != '/onboarding') {
    return '/onboarding';
  }
  return null;
}