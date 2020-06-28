<template>
  <div class="item-inner">
    <span>{{ source.name }}</span>
  </div>
</template>

<script>
export default {
  name: 'FixSizeItem',
  props: {
    source: {
      type: Object,
      default() {
        return {};
      },
    },
  },
};
</script>

<style lang="less" scoped>
.item-inner {
  span:first-child {
    margin-right: 1em;
  }
}
</style>
