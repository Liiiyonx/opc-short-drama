<template>
  <div class="page">
    <el-empty :description="`${title}建设中`">
      <template #description>
        <p>{{ title }}</p>
        <p style="font-size: 13px; color: var(--el-text-color-secondary)">{{ note }}</p>
      </template>
    </el-empty>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '该端' },
  note: { type: String, default: '按开发计划推进中' }
})
</script>

<style scoped>
.page {
  padding: 24px;
}
</style>
