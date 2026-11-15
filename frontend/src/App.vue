<template>
  <el-config-provider :locale="zhCn">
    <AppHeader v-if="showHeader" />
    <router-view v-slot="{ Component }">
      <transition name="page-fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </el-config-provider>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import AppHeader from './components/AppHeader.vue'

const route = useRoute()
// 登录页不渲染顶栏（自带品牌区）
const showHeader = computed(() => !route.meta.public)
</script>
