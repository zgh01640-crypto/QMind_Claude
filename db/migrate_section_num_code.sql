-- 给 measure_sections 加 num_code 列（6位数字编码，如 "010101"）
ALTER TABLE measure_sections ADD COLUMN IF NOT EXISTS num_code VARCHAR(20);

-- 从现有 items 反推填充，无需重新导入数据
UPDATE measure_sections ms
SET num_code = sub.prefix
FROM (
    SELECT section_id, LEFT(item_code, 6) AS prefix
    FROM measure_items
    GROUP BY section_id, LEFT(item_code, 6)
) sub
WHERE ms.id = sub.section_id AND ms.level = 2;
