<template>
  <el-steps :active="activeIndex" align-center class="work-steps">
    <el-step
      v-for="step in steps"
      :key="step.key"
      :title="step.title"
      :description="step.desc"
      :status="step.status"
    />
  </el-steps>
</template>

<script setup>
defineProps({
  steps: { type: Array, required: true },
  activeIndex: { type: Number, default: 0 }
})
</script>

<style scoped>
.work-steps {
  margin: 20px 0 28px;
}
</style>
