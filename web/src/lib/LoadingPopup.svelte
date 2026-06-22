<script>
  let { message = "Loading..." } = $props();
</script>

<div class="loading">
  <div class="spinner"></div>
  <p>{message}</p>
</div>

<style>
  .loading {
    text-align: center;
    padding: 2rem;
    color: #7c7c9a;
  }
  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid #333;
    border-top-color: #7c7c9a;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto 1rem;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  p {
    font-family: monospace;
    font-size: 0.9rem;
  }
</style>
