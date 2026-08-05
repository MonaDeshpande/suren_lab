-- Allow basic_nutrition package type (alias for legacy nutrition_only).
-- Food packages: product name + package_type → subset of Food catalog tests.

ALTER TABLE sample_test_packages
    DROP CONSTRAINT IF EXISTS sample_test_packages_package_type_check;

ALTER TABLE sample_test_packages
    ADD CONSTRAINT sample_test_packages_package_type_check
    CHECK (package_type IN (
        'fssai', 'nutrition_only', 'basic_nutrition', 'detailed_nutrition'
    ));

ALTER TABLE request_samples
    DROP CONSTRAINT IF EXISTS request_samples_package_type_check;

ALTER TABLE request_samples
    ADD CONSTRAINT request_samples_package_type_check
    CHECK (
        package_type IS NULL
        OR package_type IN (
            'fssai', 'nutrition_only', 'basic_nutrition', 'detailed_nutrition'
        )
    );

ALTER TABLE custom_formulas
    DROP CONSTRAINT IF EXISTS custom_formulas_package_type_check;

ALTER TABLE custom_formulas
    ADD CONSTRAINT custom_formulas_package_type_check
    CHECK (
        package_type IS NULL
        OR package_type IN (
            'fssai', 'nutrition_only', 'basic_nutrition', 'detailed_nutrition'
        )
    );
