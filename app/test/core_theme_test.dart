import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:business_ai_robot/core/theme/theme.dart';
import 'package:business_ai_robot/core/config/config.dart';

void main() {
  group('AppColors Tests', () {
    test('Verify all color constants and hex values', () {
      expect(AppColors.primary, const Color(0xFF007AFF));
      expect(AppColors.primaryLight, const Color(0xFFE8F4FD));
      expect(AppColors.background, const Color(0xFFFFFFFF));
      expect(AppColors.surface, const Color(0xFFF8F9FA));
      expect(AppColors.surfaceVariant, const Color(0xFFF2F3F5));
      expect(AppColors.textPrimary, const Color(0xFF1A1A1A));
      expect(AppColors.textSecondary, const Color(0xFF6B7280));
      expect(AppColors.textTertiary, const Color(0xFF9CA3AF));
      expect(AppColors.border, const Color(0xFFE5E7EB));
      expect(AppColors.borderLight, const Color(0xFFF0F0F0));
      expect(AppColors.divider, const Color(0xFFF3F4F6));
      expect(AppColors.success, const Color(0xFF34C759));
      expect(AppColors.successLight, const Color(0xFFEBFBF0));
      expect(AppColors.warning, const Color(0xFFFF9500));
      expect(AppColors.warningLight, const Color(0xFFFFF8EC));
      expect(AppColors.error, const Color(0xFFFF3B30));
      expect(AppColors.errorLight, const Color(0xFFFEECEB));
      expect(AppColors.online, const Color(0xFF34C759));
      expect(AppColors.offline, const Color(0xFFFF3B30));
      expect(AppColors.shadow, const Color(0x0A000000));
    });
  });

  group('AppSpacing Tests', () {
    test('Verify all spacing and radius constants', () {
      expect(AppSpacing.xs, 4.0);
      expect(AppSpacing.sm, 8.0);
      expect(AppSpacing.md, 12.0);
      expect(AppSpacing.lg, 16.0);
      expect(AppSpacing.xl, 20.0);
      expect(AppSpacing.xxl, 24.0);
      expect(AppSpacing.xxxl, 32.0);
      expect(AppSpacing.screenPadding, 20.0);
      expect(AppSpacing.cardPadding, 16.0);
      expect(AppSpacing.sectionGap, 24.0);
      expect(AppSpacing.borderRadiusSm, 8.0);
      expect(AppSpacing.borderRadius, 12.0);
      expect(AppSpacing.borderRadiusLg, 16.0);
      expect(AppSpacing.borderRadiusXl, 20.0);
    });
  });

  group('AppTypography Tests', () {
    test('Verify typography styles as values and invocations', () {
      expect(AppTypography.displayLarge.fontSize, 28.0);
      expect(AppTypography.displayLarge.fontWeight, FontWeight.w700);
      expect(AppTypography.displayLarge.color, AppColors.textPrimary);

      expect(AppTypography.displayMedium.fontSize, 24.0);
      expect(AppTypography.displayMedium.fontWeight, FontWeight.w700);
      expect(AppTypography.displayMedium.color, AppColors.textPrimary);

      expect(AppTypography.headlineLarge.fontSize, 20.0);
      expect(AppTypography.headlineLarge.fontWeight, FontWeight.w600);
      expect(AppTypography.headlineLarge.color, AppColors.textPrimary);

      expect(AppTypography.headlineMedium.fontSize, 18.0);
      expect(AppTypography.headlineMedium.fontWeight, FontWeight.w600);
      expect(AppTypography.headlineMedium.color, AppColors.textPrimary);

      expect(AppTypography.titleLarge.fontSize, 17.0);
      expect(AppTypography.titleLarge.fontWeight, FontWeight.w600);
      expect(AppTypography.titleLarge.color, AppColors.textPrimary);

      expect(AppTypography.titleMedium.fontSize, 16.0);
      expect(AppTypography.titleMedium.fontWeight, FontWeight.w500);
      expect(AppTypography.titleMedium.color, AppColors.textPrimary);

      expect(AppTypography.bodyLarge.fontSize, 16.0);
      expect(AppTypography.bodyLarge.fontWeight, FontWeight.w400);
      expect(AppTypography.bodyLarge.color, AppColors.textPrimary);

      expect(AppTypography.bodyMedium.fontSize, 15.0);
      expect(AppTypography.bodyMedium.fontWeight, FontWeight.w400);
      expect(AppTypography.bodyMedium.color, AppColors.textPrimary);

      expect(AppTypography.bodySmall.fontSize, 14.0);
      expect(AppTypography.bodySmall.fontWeight, FontWeight.w400);
      expect(AppTypography.bodySmall.color, AppColors.textSecondary);

      expect(AppTypography.caption.fontSize, 13.0);
      expect(AppTypography.caption.fontWeight, FontWeight.w400);
      expect(AppTypography.caption.color, AppColors.textSecondary);

      expect(AppTypography.captionSmall.fontSize, 12.0);
      expect(AppTypography.captionSmall.fontWeight, FontWeight.w400);
      expect(AppTypography.captionSmall.color, AppColors.textTertiary);

      expect(AppTypography.statValue.fontSize, 28.0);
      expect(AppTypography.statValue.fontWeight, FontWeight.w700);
      expect(AppTypography.statValue.color, AppColors.textPrimary);

      expect(AppTypography.statLabel.fontSize, 13.0);
      expect(AppTypography.statLabel.fontWeight, FontWeight.w500);
      expect(AppTypography.statLabel.color, AppColors.textSecondary);
      expect(AppTypography.statLabel.letterSpacing, 0.3);

      // Verify callable method behavior
      final modified = AppTypography.headlineMedium(color: AppColors.primary);
      expect(modified.color, AppColors.primary);
      expect(modified.fontSize, 18.0);
    });
  });

  group('AppTheme Tests', () {
    test('Verify Material 3 theme properties', () {
      final theme = AppTheme.lightTheme;
      expect(theme.useMaterial3, isTrue);
      expect(theme.scaffoldBackgroundColor, AppColors.surface);
      expect(theme.appBarTheme.backgroundColor, AppColors.background);
      expect(theme.appBarTheme.elevation, 0.0);
      expect(theme.cardTheme.color, AppColors.background);
      expect(theme.cardTheme.elevation, 0.0);
      expect(theme.bottomNavigationBarTheme.backgroundColor, AppColors.background);
      expect(theme.bottomNavigationBarTheme.selectedItemColor, AppColors.primary);
      expect(theme.dividerTheme.color, AppColors.divider);
    });
  });

  group('AppConfig Tests', () {
    test('Verify configuration constants', () {
      expect(AppConfig.appName, 'Business AI Robot');
      expect(AppConfig.appVersion, '0.1.0');
      expect(AppConfig.apiBaseUrl, 'http://localhost:8000');
      expect(AppConfig.apiPrefix, '/api/v1');
      expect(AppConfig.fullApiUrl, 'http://localhost:8000/api/v1');
    });
  });

  group('ApiEndpoints Tests', () {
    test('Verify static API routes and parameterized methods', () {
      expect(ApiEndpoints.health, '/health');
      expect(ApiEndpoints.robots, '/robots');
      expect(ApiEndpoints.robotStatus('alpha-1'), '/robots/alpha-1/status');
      expect(ApiEndpoints.robotHeartbeat('alpha-1'), '/robots/alpha-1/heartbeat');
      expect(ApiEndpoints.products, '/products');
      expect(ApiEndpoints.customers, '/customers');
      expect(ApiEndpoints.bills, '/bills');
      expect(ApiEndpoints.payments, '/payments');
      expect(ApiEndpoints.reminders, '/reminders');
      expect(ApiEndpoints.reports, '/reports');
      expect(ApiEndpoints.aiProcess, '/ai/process');
    });
  });
}
